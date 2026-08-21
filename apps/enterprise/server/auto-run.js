// AI 自动运行模拟器（Auto-Run Simulator）
// 通过 dsh Harness 的 HTTP 信封 API 直驱真实模型（LM Studio Qwen3.8-27B）：
// 多 Agent 角色各自持有持久 dsh 会话轮跑问答；dsh 工作区 = 各企业功能清单目录。
// 全部执行落库（data_origin='auto-simulated'），由「AI 运行监控」页实时展示。
import { db, DATA_DIR } from './db.js'
import { randomUUID } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { FUNCTION_CATALOG, featureRoles } from './function-catalog.js'

const ORIGIN = 'auto-simulated'
const MODEL_LABEL = 'Qwen3.8-27B · dsh Harness'
const TURN_TIMEOUT_MS = 600_000 // 27B 本地模型多工具调用一轮可能数分钟
const POLL_MS = 3_000

const sleep = ms => new Promise(r => setTimeout(r, ms))
const now = () => new Date().toISOString().replace('T', ' ').slice(0, 19)
/** 运行日志（stderr，随服务进程重定向到文件），排查直驱链路卡点 */
const trace = msg => console.error(`[autorun ${now()}] ${msg}`)
// 惰性 prepare：模块加载早于 init() 建表，语句必须在使用时才创建
let _insMessage = null
const insMessage = (conversationId, role, content) => {
  _insMessage ??= db.prepare('INSERT INTO runtime_message (conversation_id, role, content, created_at, data_origin) VALUES (?,?,?,?,?)')
  _insMessage.run(conversationId, role, content, now(), ORIGIN)
}

// ---------------------------------------------------------------------------
// dsh 信封客户端（loopback 免鉴权；响应恒 200，业务错误在 result.ok 里）
// ---------------------------------------------------------------------------

function dshBase () {
  const url = db.prepare("SELECT value FROM business_setting WHERE key = 'dsh.url'").get()?.value || 'http://127.0.0.1:8308'
  return url.replace(/\/+$/, '')
}

async function rpc (method, payload, timeoutMs = 30_000) {
  const res = await fetch(`${dshBase()}/api/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method, payload }),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new Error(`dsh ${method}: HTTP ${res.status}`)
  const body = await res.json()
  const result = body?.result
  if (!result?.ok) throw new Error(`dsh ${method}: ${result?.error?.code ?? ''} ${result?.error?.message ?? 'no result'}`)
  return result.value
}

// ---------------------------------------------------------------------------
// 审批/问题自动应答器：WebSocket 下行链路 /api/events.mux（dsh 真实 webserver
// 的 GET 返回 426，事件流走 WS 升级；服务端只下发，应答经 POST /api/respond）
// ---------------------------------------------------------------------------

const activeSessions = new Set()
let muxAbort = null

async function respond (rpcId, value) {
  const res = await fetch(`${dshBase()}/api/respond`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-response', rpcId, result: { ok: true, value } }),
    signal: AbortSignal.timeout(10_000),
  })
  return res.json().catch(() => null)
}

async function handleMuxFrame (frame) {
  if (frame?.type !== 'server-request') return
  const p = frame.payload ?? {}
  if (frame.method === 'approval/requested') {
    if (!activeSessions.has(p.sessionId)) return
    trace(`审批自动放行: ${p.toolName} (${p.sessionId.slice(0, 20)}…)`)
    const receipt = await respond(frame.rpcId, { sessionId: p.sessionId, approvalId: p.approvalId, outcome: 'allowed-once' })
    if (receipt && receipt.accepted === false) trace(`审批应答回执: ${receipt.reason}`)
  } else if (frame.method === 'question/requested') {
    // 模型违规向用户提问（ask_user_question）→ 自动作答继续，避免 turn 永久挂起
    if (!activeSessions.has(p.sessionId)) return
    const questions = p.questions ?? []
    trace(`模型提问自动应答: ${questions.length} 个问题 (${p.sessionId.slice(0, 20)}…)`)
    const value = {
      sessionId: p.sessionId,
      answer: { answers: questions.map(q => ({ id: q.id, selected: q.options?.length ? [q.options[0].label] : [], custom: '请基于已有信息直接继续，无需向用户提问。' })) },
    }
    const receipt = await respond(frame.rpcId, value)
    if (receipt && receipt.accepted === false) trace(`问题应答回执: ${receipt.reason}`)
  }
}

/** 后台启动 WS 监听（永不 resolve 的守护循环，调用方必须 void 而非 await） */
function startApprovalListener () {
  if (muxAbort) return
  muxAbort = new AbortController()
  const { signal } = muxAbort
  const wsUrl = dshBase().replace(/^http/, 'ws') + '/api/events.mux'
  trace(`WS 审批/问题监听启动 → ${wsUrl}`)
  const loop = async () => {
    while (!signal.aborted) {
      await new Promise(resolve => {
        let opened = false
        const ws = new WebSocket(wsUrl)
        const onAbort = () => { try { ws.close() } catch { /* already closed */ }; resolve() }
        signal.addEventListener('abort', onAbort, { once: true })
        ws.onopen = () => { opened = true; trace('WS 已连接') }
        ws.onmessage = ev => {
          try { void handleMuxFrame(JSON.parse(String(ev.data))) } catch (e) { trace(`帧处理异常: ${e.message}`) }
        }
        ws.onclose = () => { signal.removeEventListener('abort', onAbort); resolve() }
        ws.onerror = () => { if (!opened) signal.removeEventListener('abort', onAbort), resolve() }
      })
      if (signal.aborted) return
      trace('WS 断开，3s 后重连')
      await sleep(3_000)
    }
  }
  loop().catch(e => trace(`WS 监听循环异常: ${e.message}`))
}

function stopApprovalListener () {
  if (muxAbort) { muxAbort.abort(); muxAbort = null; trace('WS 监听已停止') }
}

// ---------------------------------------------------------------------------
// 工作区（每租户一个目录 = dsh 工作区 = 该企业功能清单）
// ---------------------------------------------------------------------------

function getTenant (code) {
  const t = db.prepare('SELECT id, code, name FROM business_tenant WHERE code = ?').get(code)
  if (!t) throw new Error(`租户不存在: ${code}`)
  return t
}

function tenantWorkspaceDir (tenant) {
  return join(DATA_DIR, 'workspaces', tenant.code)
}

/** 金汉隆近一月发票聚合 → markdown（工作区 data.md，供模型阅读分析） */
function jhlDataMarkdown () {
  const anchor = db.prepare('SELECT MAX(invoice_date) AS d FROM business_invoice WHERE tenant_id = 4').get()?.d
  if (!anchor) return '# 近一月采购数据\n\n（暂无发票数据）\n'
  const rows = db.prepare(`
    SELECT invoice_no, invoice_date, supplier, category, amount_excl_tax, tax, amount_total
    FROM business_invoice WHERE tenant_id = 4
      AND invoice_date >= date(?, '-31 days') ORDER BY invoice_date`).all(anchor)
  const used = rows.length ? rows : db.prepare('SELECT invoice_no, invoice_date, supplier, category, amount_excl_tax, tax, amount_total FROM business_invoice WHERE tenant_id = 4 ORDER BY invoice_date').all()
  const window = rows.length ? `数据窗口：${anchor} 往前 31 天（发票 ${used.length} 张）` : `数据窗口：全部发票（${used.length} 张，近一月无新发票，回退全量）`
  const total = used.reduce((s, r) => s + r.amount_total, 0)
  const bySupplier = {}
  const byCategory = {}
  for (const r of used) {
    bySupplier[r.supplier] = (bySupplier[r.supplier] || 0) + r.amount_total
    byCategory[r.category] = (byCategory[r.category] || 0) + r.amount_total
  }
  const items = db.prepare(`
    SELECT i.item_name, i.spec, i.qty, i.unit_price, i.amount
    FROM business_invoice_item i JOIN business_invoice h ON h.invoice_id = i.invoice_id
    WHERE h.tenant_id = 4 AND h.invoice_date >= date(?, '-31 days')`).all(anchor)
  const usedItems = items.length ? items : db.prepare(`
    SELECT i.item_name, i.spec, i.qty, i.unit_price, i.amount
    FROM business_invoice_item i JOIN business_invoice h ON h.invoice_id = i.invoice_id
    WHERE h.tenant_id = 4`).all()
  const topItems = [...usedItems].sort((a, b) => b.amount - a.amount).slice(0, 12)
  const fmt = n => '¥' + Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `# 金汉隆近一月采购数据（data.md）

${window}

## 总体规模
- 价税合计：**${fmt(total)}**（不含税 ${fmt(used.reduce((s, r) => s + r.amount_excl_tax, 0))}，税额 ${fmt(used.reduce((s, r) => s + r.tax, 0))}）

## 供应商汇总
| 供应商 | 价税合计 | 占比 |
|---|---|---|
${Object.entries(bySupplier).sort((a, b) => b[1] - a[1]).map(([k, v]) => `| ${k} | ${fmt(v)} | ${(v / total * 100).toFixed(1)}% |`).join('\n')}

## 品类结构
| 品类 | 价税合计 |
|---|---|
${Object.entries(byCategory).sort((a, b) => b[1] - a[1]).map(([k, v]) => `| ${k} | ${fmt(v)} |`).join('\n')}

## 高额物料 TOP12
| 物料 | 规格 | 数量 | 单价 | 金额 |
|---|---|---|---|---|
${topItems.map(r => `| ${r.item_name} | ${r.spec || '-'} | ${r.qty} | ${fmt(r.unit_price)} | ${fmt(r.amount)} |`).join('\n')}

## 发票明细
| 发票号 | 日期 | 供应商 | 品类 | 价税合计 |
|---|---|---|---|---|
${used.map(r => `| ${r.invoice_no} | ${r.invoice_date} | ${r.supplier} | ${r.category} | ${fmt(r.amount_total)} |`).join('\n')}
`
}

/** 生成租户功能清单 FUNCTIONS.md（含功能授权、Agent、数据概况） */
function writeFunctionsDoc (tenant) {
  const features = db.prepare(`
    SELECT f.code, f.name FROM business_tenant_feature tf
    JOIN business_feature f ON f.code = tf.feature_code
    WHERE tf.tenant_id = ? AND tf.enabled = 1`).all(tenant.id)
  const agents = db.prepare(`
    SELECT agent_name, agent_type, model FROM business_agent WHERE tenant_id = ? AND status = 'published'`).all(tenant.id)
  const counts = {}
  for (const [tbl, label] of [['business_order', '订单'], ['business_customer', '客户'], ['business_inventory', '库存记录'], ['business_after_sale', '售后工单']]) {
    try { counts[label] = db.prepare(`SELECT COUNT(*) AS c FROM ${tbl} WHERE tenant_id = ?`).get(tenant.id).c } catch { /* 表可能无租户列 */ }
  }
  const lines = [
    `# ${tenant.name} · 企业功能清单（FUNCTIONS.md）`,
    '',
    '本文件是本企业在智造云平台的数字化功能清单，由平台自动生成。AI 助手在回答本企业相关问题时应先阅读本文件。',
    '',
    '## 已开通功能模块',
    ...(features.length ? features.map(f => `- **${f.name}**（${f.code}）`) : ['- （暂无）']),
    '',
    '## 在册 AI Agent',
    ...(agents.length ? agents.map(a => `- **${a.agent_name}**（类型 ${a.agent_type}，模型 ${a.model}）`) : ['- （暂无）']),
    '',
    '## 业务数据概况',
    ...Object.entries(counts).map(([k, v]) => `- ${k}：${v} 条`),
  ]
  if (tenant.code === 'jhl') {
    lines.push('', '## 近一月采购数据', '详见工作区内 `data.md`（增值税专用发票与物料明细聚合，由平台自动导出）。')
  }
  lines.push('')
  return lines.join('\n')
}

const workspaceCache = new Map() // tenantId -> { workspaceId }

async function ensureWorkspace (tenant) {
  if (workspaceCache.has(tenant.id)) return workspaceCache.get(tenant.id)
  const dir = tenantWorkspaceDir(tenant)
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'FUNCTIONS.md'), writeFunctionsDoc(tenant), 'utf8')
  if (tenant.code === 'jhl') writeFileSync(join(dir, 'data.md'), jhlDataMarkdown(), 'utf8')
  const value = await rpc('workspace.create', { path: dir })
  const workspaceId = value.workspace?.workspaceId ?? value.workspaceId
  if (!workspaceId) throw new Error('workspace.create 未返回 workspaceId')
  const entry = { workspaceId, dir }
  workspaceCache.set(tenant.id, entry)
  return entry
}

/** 幂等会话：sessionId 持久化在 business_setting，8308 重启后冷恢复仍有效 */
async function ensureSession (tenant, roleKey) {
  const settingKey = `auto.session.${tenant.id}.${roleKey}`
  const saved = db.prepare('SELECT value FROM business_setting WHERE key = ?').get(settingKey)?.value
  const workspace = await ensureWorkspace(tenant)
  if (saved) {
    try {
      await rpc('session.create', { sessionId: saved, workspaceId: workspace.workspaceId })
      return saved
    } catch { /* 会话已失效则重新创建 */ }
  }
  const sessionId = `session-${randomUUID()}`
  await rpc('session.create', { sessionId, workspaceId: workspace.workspaceId })
  db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at')
    .run(settingKey, sessionId, now())
  return sessionId
}

// ---------------------------------------------------------------------------
// 轮次执行：prompt → 轮询 history 至 turn/end
// ---------------------------------------------------------------------------

function extractAssistantText (entries) {
  let text = ''
  for (const { event } of entries) {
    if (event.type !== 'assistant/message') continue
    const content = event.data?.message?.content
    if (!Array.isArray(content)) continue
    const t = content.filter(b => b?.type === 'text').map(b => b.text).join('').trim()
    if (t) text = t
  }
  return text
}

function collectTools (entries) {
  const tools = []
  for (const { event } of entries) {
    if (event.type === 'tool/call') {
      tools.push({ name: event.data?.name ?? 'tool', input: String(event.data?.arguments ?? '') })
    } else if (event.type === 'tool/result') {
      const blocks = event.data?.message?.content
      if (Array.isArray(blocks)) {
        const t = blocks.filter(b => b?.type === 'text').map(b => b.text).join('')
        const last = tools[tools.length - 1]
        if (last && t) last.output = t.slice(0, 2_000)
      }
    }
  }
  return tools
}

async function runTurn (sessionId, text) {
  const startedAt = Date.now()
  trace(`runTurn 开始 (${sessionId.slice(0, 20)}…): ${text.slice(0, 50)}…`)
  const tail = await rpc('session.history', { sessionId, maxMessages: 1 })
  let baseline = -1
  for (const e of tail.events ?? []) baseline = Math.max(baseline, e.event.seq)
  trace(`baseline seq=${baseline}`)
  const promptRes = await rpc('session.prompt', { sessionId, mode: 'queue', content: [{ type: 'text', text }] })
  trace(`prompt 已提交: ${JSON.stringify(promptRes)}`)
  const deadline = startedAt + TURN_TIMEOUT_MS
  let polls = 0
  while (Date.now() < deadline) {
    await sleep(POLL_MS)
    polls += 1
    const page = await rpc('session.history', { sessionId, maxMessages: 20 })
    const fresh = (page.events ?? []).filter(e => e.event.seq > baseline)
    const end = fresh.find(e => e.event.type === 'turn/end')
    if (end) {
      trace(`turn 结束 (${polls} 次轮询, ${Date.now() - startedAt}ms): reason=${end.event.data?.reason?.kind}`)
      return {
        ok: true,
        reason: end.event.data?.reason?.kind ?? 'unknown',
        text: extractAssistantText(fresh),
        tools: collectTools(fresh),
        latencyMs: Date.now() - startedAt,
      }
    }
    if (polls % 10 === 1) {
      const last = fresh[fresh.length - 1]
      trace(`轮询中 #${polls}: ${fresh.length} 新事件, 最新=${last?.event.type ?? '无'}`)
    }
  }
  trace(`runTurn 超时，执行 cancel`)
  await rpc('session.cancel', { sessionId }).catch(() => {})
  throw new Error(`单轮超时（${TURN_TIMEOUT_MS / 1000}s），已取消`)
}

// ---------------------------------------------------------------------------
// 落库
// ---------------------------------------------------------------------------

const settingUpsert = () => db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at')

function resolveAgentId (tenantId, agentName) {
  const exact = db.prepare("SELECT agent_id FROM business_agent WHERE tenant_id = ? AND agent_name = ? AND status = 'published'").get(tenantId, agentName)
  if (exact) return exact.agent_id
  return db.prepare("SELECT agent_id FROM business_agent WHERE tenant_id = ? AND status = 'published' LIMIT 1").get(tenantId)?.agent_id ?? null
}

function tenantUserId (tenantId) {
  return db.prepare("SELECT id FROM business_user WHERE tenant_id = ? AND status = 'active' ORDER BY role = 'tenant_admin' DESC, id ASC LIMIT 1").get(tenantId)?.id ?? null
}

/** 持久对话（每 tenant×roleKey 一条），消息持续累积供监控页展示 */
function ensureConversation (tenantId, roleKey, title, agentId) {
  const key = `auto.conv.${tenantId}.${roleKey}`
  const saved = db.prepare('SELECT value FROM business_setting WHERE key = ?').get(key)?.value
  if (saved && db.prepare('SELECT id FROM runtime_conversation WHERE id = ?').get(Number(saved))) return Number(saved)
  const r = db.prepare('INSERT INTO runtime_conversation (tenant_id, user_id, agent_id, title, created_at, data_origin) VALUES (?,?,?,?,?,?)')
    .run(tenantId, tenantUserId(tenantId), agentId, title, now(), ORIGIN)
  const id = Number(r.lastInsertRowid)
  settingUpsert().run(key, String(id), now())
  return id
}

/** 一轮执行落库：execution + 消息 + 工具调用 + 模型用量（data_origin=auto-simulated） */
function logRound ({ tenant, agentName, roleKey, roleTitle, question, turn, triggerType, error = null, feature = null, module = null }) {
  const agentId = agentName ? resolveAgentId(tenant.id, agentName) : null
  const traceId = randomUUID()
  const convId = ensureConversation(tenant.id, roleKey, feature ? `${feature} · 功能演示` : `${roleTitle} · 自动运行`, agentId)
  const t = now()
  const ok = !error && turn?.ok
  insMessage(convId, 'user', question)
  if (ok) insMessage(convId, 'assistant', turn.text || '（空回复）')
  const tokenIn = Math.ceil((question.length ?? 0) / 3)
  const tokenOut = Math.ceil((turn?.text?.length ?? 0) / 3)
  const r = db.prepare(`INSERT INTO runtime_agent_execution (trace_id, tenant_id, user_id, agent_id, trigger_type, input, output, status, started_at, finished_at, latency_ms, model, token_input, token_output, error, data_origin)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(traceId, tenant.id, tenantUserId(tenant.id), agentId, triggerType,
      JSON.stringify({ instruction: question, role: roleTitle, ...(feature ? { feature } : {}), ...(module ? { module } : {}) }),
      ok ? (turn.text || '') : null,
      ok ? 'success' : 'failed', t, now(), turn?.latencyMs ?? null, MODEL_LABEL,
      tokenIn, tokenOut, ok ? null : String(error ?? turn?.reason ?? 'empty reply'), ORIGIN)
  const execId = Number(r.lastInsertRowid)
  for (const tool of turn?.tools ?? []) {
    db.prepare('INSERT INTO runtime_tool_execution (trace_id, execution_id, tenant_id, tool_name, input, output, status, execution_time_ms, created_at, data_origin) VALUES (?,?,?,?,?,?,?,?,?,?)')
      .run(traceId, execId, tenant.id, tool.name, tool.input ?? null, tool.output ?? null, 'success', null, t, ORIGIN)
  }
  if (ok) db.prepare('INSERT INTO runtime_model_usage (tenant_id, execution_id, model, token_input, token_output, created_at, data_origin) VALUES (?,?,?,?,?,?,?)')
    .run(tenant.id, execId, MODEL_LABEL, tokenIn, tokenOut, t, ORIGIN)
  return { executionId: execId, traceId }
}

// ---------------------------------------------------------------------------
// 角色注册表与问题库（多 Agent 角色轮跑，同一本地模型）
// ---------------------------------------------------------------------------

const GUARD = '请先阅读工作区中的 FUNCTIONS.md 再作答，直接给出结论与建议，不要向用户提问。'

const ROLES = [
  {
    key: 'purchase-jhl', name: '采购分析师', tenantCode: 'jhl', agentName: '采购分析 Agent',
    questions: [
      '请概括近一月采购总额与主要供应商结构，指出集中度风险。',
      '请基于 data.md 找出金额最高的三类物料，评估其价格合理性并给出议价建议。',
      '请按供应商维度分析近一月采购份额，预测下月采购支出并给出成本优化建议。',
    ],
    dataDoc: true,
  },
  {
    key: 'assistant-jhl', name: '企业智能助手', tenantCode: 'jhl', agentName: '企业智能助手',
    questions: [
      '请概括本企业当前已开通的数字化功能模块与在册 Agent，评估数字化成熟度。',
      '请总结 data.md 中近一月经营数据要点，给出三条经营改进建议。',
      '如果企业希望加强采购管控，基于现有功能清单给出一份分阶段落地路线图。',
    ],
    dataDoc: true,
  },
  {
    key: 'risk-a', name: '风控专员', tenantCode: 'corp-a', agentName: '交付风险预警 Agent',
    questions: [
      '请基于本企业功能清单，设计一套订单交付风险监控方案，列出需要重点跟踪的指标与阈值。',
      '请为本企业写一份风险日报模板，覆盖订单延迟、库存告警与售后异常三个维度。',
    ],
  },
  {
    key: 'assistant-a', name: '企业智能助手', tenantCode: 'corp-a', agentName: '企业智能助手',
    questions: [
      '请概括本企业功能清单，并给出下一步数字化提升的三个优先事项。',
      '请基于功能清单为管理层写一段 200 字以内的经营周报摘要框架。',
    ],
  },
  {
    key: 'finance-b', name: '财务顾问', tenantCode: 'corp-b', agentName: '企业日报 Agent',
    questions: [
      '请基于功能清单设计一份月度经营分析报告框架（含订单、财务、售后维度）。',
      '请为本企业梳理财务与订单数据联动的三个分析场景及所需指标。',
    ],
  },
  {
    key: 'assistant-c', name: '企业智能助手', tenantCode: 'corp-c', agentName: '企业智能助手',
    questions: [
      '请概括本企业功能清单，并指出当前功能覆盖的空白点。',
      '请为本企业规划一个季度内的 AI 应用落地计划（基于功能清单与在册 Agent）。',
    ],
  },
]

function roleQuestion (role, roundIdx) {
  // 功能演示角色：问题本身已含身份指令（来自功能清单），直接使用
  if (role.feature) return role.questions[roundIdx % role.questions.length]
  const q = role.questions[roundIdx % role.questions.length]
  const doc = role.dataDoc ? '（经营数据在工作区 data.md）' : ''
  return `作为${role.name}${doc}，${q} ${GUARD}`
}

/** 全量角色库：业务角色（6）+ 功能模块演示角色（28，来自产品功能清单，跨租户轮转） */
function buildRoster (scope = 'all') {
  const tenantCodes = db.prepare("SELECT code FROM business_tenant WHERE status = 'active'").all().map(r => r.code)
  const features = featureRoles(tenantCodes)
  if (scope === 'business') return ROLES
  if (scope === 'features') return features
  return [...ROLES, ...features]
}

// ---------------------------------------------------------------------------
// 状态机与 worker pool
// ---------------------------------------------------------------------------

const S = {
  state: 'idle', // idle | running | stopping
  runId: 0, startedAt: null, finishedAt: null, cfg: null,
  roles: [], errors: [], done: 0, failed: 0, total: 0,
  report: { running: false, generatedAt: null, error: null },
  multiagent: { running: false, finishedAt: null, error: null },
}

export function autoRunStatus () {
  return {
    state: S.state, runId: S.runId, startedAt: S.startedAt, finishedAt: S.finishedAt,
    done: S.done, failed: S.failed, total: S.total,
    roles: S.roles.map(r => ({ key: r.key, name: r.name, tenant: r.tenant, done: r.done, failed: r.failed, rounds: r.rounds, current: r.current, feature: r.feature ?? null })),
    roster: buildRoster('all').map(r => ({ key: r.key, name: r.name, tenant: getTenant(r.tenantCode).name, questions: r.questions.length, feature: r.feature ?? null, module: r.module ?? null })),
    errors: S.errors.slice(-10),
    report: { ...S.report, generatedAt: reportGeneratedAt() },
    multiagent: S.multiagent,
    dsh: dshBase(),
  }
}

function noteError (msg) {
  S.errors.push({ at: now(), message: String(msg).slice(0, 300) })
  if (S.errors.length > 50) S.errors.shift()
}

async function askRole (role, roundIdx) {
  const tenant = getTenant(role.tenantCode)
  role.current = role.questions[roundIdx % role.questions.length]
  trace(`角色轮次开始: ${role.name}@${tenant.code} 第${roundIdx + 1}轮${role.feature ? `（功能: ${role.feature}）` : ''}`)
  const sessionId = await ensureSession(tenant, role.key)
  activeSessions.add(sessionId)
  const extra = { feature: role.feature ?? null, module: role.module ?? null }
  try {
    const question = roleQuestion(role, roundIdx)
    const turn = await runTurn(sessionId, question)
    logRound({ tenant, agentName: role.agentName, roleKey: role.key, roleTitle: role.name, question, turn, triggerType: 'auto:sim', ...extra })
    role.done += 1
    S.done += 1
    trace(`角色轮次完成: ${role.name} 第${roundIdx + 1}轮 (${turn.latencyMs}ms, ${turn.text.length} 字)`)
  } catch (e) {
    trace(`角色轮次失败: ${role.name} 第${roundIdx + 1}轮: ${e.message}`)
    logRound({ tenant, agentName: role.agentName, roleKey: role.key, roleTitle: role.name, question: roleQuestion(role, roundIdx), turn: null, triggerType: 'auto:sim', error: e.message, ...extra })
    role.failed += 1
    S.failed += 1
    noteError(`${role.name}: ${e.message}`)
  } finally {
    role.current = null
    activeSessions.delete(sessionId)
  }
}

export function startAutoRun (cfg = {}) {
  if (S.state === 'running') { const e = new Error('模拟器正在运行中'); e.status = 409; throw e }
  const rounds = Math.max(1, Math.min(Number(cfg.rounds) || 3, 10))
  const concurrency = Math.max(1, Math.min(Number(cfg.concurrency) || 2, 4))
  const scope = ['all', 'business', 'features'].includes(cfg.scope) ? cfg.scope : 'all'
  const roster = buildRoster(scope)
  S.state = 'running'; S.runId += 1; S.startedAt = now(); S.finishedAt = null
  S.done = 0; S.failed = 0; S.errors = []; S.cfg = { rounds, concurrency, scope }
  S.roles = roster.map(r => ({ ...r, tenant: getTenant(r.tenantCode).name, done: 0, failed: 0, rounds, current: null }))
  S.total = roster.length * rounds
  void startApprovalListener()
  // 任务队列（角色×轮次交错，保证各角色均衡推进）
  const queue = []
  for (let i = 0; i < rounds; i++) for (const role of S.roles) queue.push({ role, roundIdx: i })
  const run = async () => {
    const workers = Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
      while (queue.length && S.state === 'running') {
        const task = queue.shift()
        if (!task) break
        await askRole(task.role, task.roundIdx)
      }
    })
    await Promise.all(workers)
    S.state = 'idle'; S.finishedAt = now()
    if (activeSessions.size === 0) stopApprovalListener()
  }
  run().catch(e => { noteError(e.message); S.state = 'idle'; S.finishedAt = now() })
  return { ok: true, roles: roster.length, rounds, concurrency, scope, total: S.total }
}

export function stopAutoRun () {
  if (S.state === 'running') S.state = 'stopping'
  stopApprovalListener()
  return { ok: true, state: S.state }
}

// ---------------------------------------------------------------------------
// 金汉隆近一月数据报告（专项任务）
// ---------------------------------------------------------------------------

function reportGeneratedAt () {
  const raw = db.prepare("SELECT value, updated_at FROM business_setting WHERE key = 'auto.report.jhl'").get()
  return raw?.updated_at ?? null
}

export function jhlReport () {
  const raw = db.prepare("SELECT value, updated_at FROM business_setting WHERE key = 'auto.report.jhl'").get()
  return { report: raw?.value ?? null, generatedAt: raw?.updated_at ?? null, running: S.report.running }
}

export async function runJhlReport () {
  if (S.report.running) return { ok: false, message: '报告生成中' }
  S.report = { running: true, generatedAt: null, error: null }
  trace('金汉隆报告任务启动')
  const tenant = getTenant('jhl')
  let sessionId = null
  try {
    // 1) 重新导出近一月发票聚合到工作区 data.md
    const dir = tenantWorkspaceDir(tenant)
    mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, 'FUNCTIONS.md'), writeFunctionsDoc(tenant), 'utf8')
    writeFileSync(join(dir, 'data.md'), jhlDataMarkdown(), 'utf8')
    trace('工作区文档已导出 (FUNCTIONS.md / data.md)')
    // 2) 报告会话分析
    sessionId = await ensureSession(tenant, 'report')
    trace(`报告会话就绪: ${sessionId}`)
    activeSessions.add(sessionId)
    void startApprovalListener()
    const question = '请阅读工作区中的 data.md（金汉隆近一月采购数据聚合），输出一份 markdown 格式的《金汉隆近一月采购数据报告》，包含：一、总体规模；二、供应商结构分析；三、品类与物料结构分析；四、风险提示；五、采购建议。直接输出报告正文，不要向用户提问。'
    const turn = await runTurn(sessionId, question)
    if (!turn.text) throw new Error('模型返回空报告')
    // 3) 存库
    settingUpsert().run('auto.report.jhl', turn.text, now())
    logRound({ tenant, agentName: '采购分析 Agent', roleKey: 'report', roleTitle: '金汉隆数据报告', question, turn, triggerType: 'auto:report' })
    S.report = { running: false, generatedAt: now(), error: null }
    trace(`报告完成 (${turn.text.length} 字, ${turn.latencyMs}ms)`)
    return { ok: true }
  } catch (e) {
    S.report = { running: false, generatedAt: null, error: e.message }
    trace(`报告失败: ${e.message}`)
    noteError(`报告生成失败: ${e.message}`)
    logRound({ tenant, agentName: '采购分析 Agent', roleKey: 'report', roleTitle: '金汉隆数据报告', question: '（生成失败）', turn: null, triggerType: 'auto:report', error: e.message })
    throw e
  } finally {
    if (sessionId) activeSessions.delete(sessionId)
    if (activeSessions.size === 0 && S.state !== 'running') stopApprovalListener()
  }
}

// ---------------------------------------------------------------------------
// 多 Agent 对话能力测试（两会话乒乓：分析师 ⇄ 智能助手）
// ---------------------------------------------------------------------------

export async function runMultiAgentTest () {
  if (S.multiagent.running) return { ok: false, message: '多 Agent 测试进行中' }
  S.multiagent = { running: true, finishedAt: null, error: null }
  const tenant = getTenant('jhl')
  const convAgentId = resolveAgentId(tenant.id, '企业智能助手')
  const convId = ensureConversation(tenant.id, 'multiagent', '多 Agent 协同测试 · 金汉隆', convAgentId)
  let a = null; let b = null
  try {
    a = await ensureSession(tenant, 'multi-a')
    b = await ensureSession(tenant, 'multi-b')
    activeSessions.add(a); activeSessions.add(b)
    void startApprovalListener()
    const read = '请先阅读工作区中的 data.md 再作答，直接给出结论，不要向用户提问。'

    // ① 分析师概括发现并向助手提问
    const q1 = `你是采购分析师。${read}请基于 data.md 概括三个关键发现，并向企业智能助手提出一个最值得深入的数据问题。`
    const t1 = await runTurn(a, q1)
    insMessage(convId, 'user', `[采购分析师] ${q1}`)
    if (t1.text) insMessage(convId, 'assistant', `[采购分析师] ${t1.text}`)
    logRound({ tenant, agentName: '采购分析 Agent', roleKey: 'multiagent-a', roleTitle: '多 Agent · 采购分析师', question: q1, turn: t1, triggerType: 'auto:multiagent' })

    // ② 助手回答分析师的问题
    const q2 = `企业智能助手你好，我是采购分析师。我向你提出以下问题：\n\n${t1.text || '（无内容）'}\n\n${read}请回答其中的问题并给出建议。`
    const t2 = await runTurn(b, q2)
    insMessage(convId, 'user', `[智能助手→收] ${q2.slice(0, 500)}`)
    if (t2.text) insMessage(convId, 'assistant', `[智能助手] ${t2.text}`)
    logRound({ tenant, agentName: '企业智能助手', roleKey: 'multiagent-b', roleTitle: '多 Agent · 智能助手', question: q2, turn: t2, triggerType: 'auto:multiagent' })

    // ③ 分析师评估收尾
    const q3 = `采购分析师继续。企业智能助手的回复如下：\n\n${t2.text || '（无内容）'}\n\n${read}请评估该回复，给出最终意见与行动清单。`
    const t3 = await runTurn(a, q3)
    insMessage(convId, 'user', `[采购分析师→收] ${q3.slice(0, 500)}`)
    if (t3.text) insMessage(convId, 'assistant', `[采购分析师] ${t3.text}`)
    logRound({ tenant, agentName: '采购分析 Agent', roleKey: 'multiagent-a', roleTitle: '多 Agent · 采购分析师', question: q3, turn: t3, triggerType: 'auto:multiagent' })

    S.multiagent = { running: false, finishedAt: now(), error: null }
    return { ok: true, turns: 3 }
  } catch (e) {
    S.multiagent = { running: false, finishedAt: null, error: e.message }
    noteError(`多 Agent 测试失败: ${e.message}`)
    throw e
  } finally {
    if (a) activeSessions.delete(a)
    if (b) activeSessions.delete(b)
    if (activeSessions.size === 0 && S.state !== 'running') stopApprovalListener()
  }
}

// ---------------------------------------------------------------------------
// 功能模块演示（AI 对话首页功能入口：点击即向租户工作区会话发送该功能的演示问题）
// ---------------------------------------------------------------------------

const featureDemoBusy = new Set() // featureIdx 去重，防连点

export async function runFeatureDemo (featureIdx, user) {
  const f = FUNCTION_CATALOG[featureIdx]
  if (!f) throw Object.assign(new Error('功能项不存在'), { status: 404 })
  if (featureDemoBusy.has(featureIdx)) throw Object.assign(new Error('该功能演示进行中'), { status: 409 })
  featureDemoBusy.add(featureIdx)
  const tenant = db.prepare('SELECT id, code, name FROM business_tenant WHERE id = ?').get(user.tenant_id)
  let sessionId = null
  try {
    sessionId = await ensureSession(tenant, 'feature-demo')
    activeSessions.add(sessionId)
    void startApprovalListener()
    trace(`功能演示开始: ${f.name}（${f.module}）@${tenant.code}`)
    const turn = await runTurn(sessionId, f.question)
    logRound({ tenant, agentName: null, roleKey: 'feature-demo', roleTitle: f.agent, question: f.question, turn, triggerType: 'auto:feature', feature: f.name, module: f.module })
    trace(`功能演示完成: ${f.name} (${turn.latencyMs}ms)`)
    return { ok: true, feature: f.name, module: f.module, reply: turn.text, latencyMs: turn.latencyMs }
  } catch (e) {
    logRound({ tenant, agentName: null, roleKey: 'feature-demo', roleTitle: f.agent, question: f.question, turn: null, triggerType: 'auto:feature', error: e.message, feature: f.name, module: f.module })
    noteError(`功能演示失败 ${f.name}: ${e.message}`)
    throw e
  } finally {
    featureDemoBusy.delete(featureIdx)
    if (sessionId) activeSessions.delete(sessionId)
    if (activeSessions.size === 0 && S.state !== 'running') stopApprovalListener()
  }
}

export function featureDemoStatus () {
  return { busy: [...featureDemoBusy] }
}

// ---------------------------------------------------------------------------
// 监控查询（platform_admin 可跨租户）
// ---------------------------------------------------------------------------

export function recentAutoExecutions (tenantId, limit = 50) {
  const cap = Math.min(Number(limit) || 50, 200)
  const where = tenantId ? 'WHERE e.tenant_id = ? AND e.trigger_type LIKE ?' : "WHERE e.trigger_type LIKE 'auto:%'"
  const args = tenantId ? [tenantId, 'auto:%'] : []
  return db.prepare(`
    SELECT e.execution_id, e.trace_id, e.tenant_id, t.name AS tenant_name, e.trigger_type, e.status,
      e.input, e.output, e.latency_ms, e.model, e.token_input, e.token_output, e.error, e.started_at
    FROM runtime_agent_execution e JOIN business_tenant t ON t.id = e.tenant_id
    ${where} ORDER BY e.execution_id DESC LIMIT ${cap}`).all(...args)
    .map(r => ({ ...r, input: r.input ? JSON.parse(r.input) : null }))
}

export function recentAutoMessages (tenantId, limit = 40) {
  const cap = Math.min(Number(limit) || 40, 100)
  const where = tenantId ? 'WHERE c.tenant_id = ? AND m.data_origin = ?' : 'WHERE m.data_origin = ?'
  const args = tenantId ? [tenantId, ORIGIN] : [ORIGIN]
  const rows = db.prepare(`
    SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, c.title, c.tenant_id, t.name AS tenant_name
    FROM runtime_message m
    JOIN runtime_conversation c ON c.id = m.conversation_id
    JOIN business_tenant t ON t.id = c.tenant_id
    ${where} ORDER BY m.id DESC LIMIT ${cap}`).all(...args)
  return rows.reverse()
}

/** 监控页聚合统计：成功率/耗时分层/Token 汇总/触发类型与角色分布/近 10 日执行趋势 */
export function autoRunAnalytics () {
  const one = (sql, p = []) => db.prepare(sql).get(...p)
  const total = one("SELECT COUNT(*) c FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%'").c
  if (total === 0) return { total: 0 }
  const success = one("SELECT COUNT(*) c FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' AND status='success'").c
  const tokens = one("SELECT COALESCE(SUM(token_input),0) i, COALESCE(SUM(token_output),0) o FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%'").c ?? 0
  const byTrigger = db.prepare(`SELECT trigger_type, COUNT(*) n, ROUND(AVG(latency_ms)) avg_ms FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' GROUP BY trigger_type`).all()
  const byTenant = db.prepare(`
    SELECT t.name tenant, COUNT(*) n, COALESCE(SUM(e.token_input+e.token_output),0) tokens
    FROM runtime_agent_execution e JOIN business_tenant t ON t.id = e.tenant_id
    WHERE e.trigger_type LIKE 'auto:%' GROUP BY e.tenant_id ORDER BY n DESC`).all()
  const byDay = db.prepare(`
    SELECT substr(started_at,1,10) d, COUNT(*) n,
      SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) ok,
      COALESCE(SUM(token_input+token_output),0) tokens
    FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%'
    GROUP BY d ORDER BY d DESC LIMIT 10`).all().reverse()
  const tools = db.prepare(`
    SELECT tool_name, COUNT(*) n FROM runtime_tool_execution
    WHERE data_origin = 'auto-simulated' GROUP BY tool_name ORDER BY n DESC LIMIT 8`).all()
  const latencyBuckets = db.prepare(`
    SELECT CASE
      WHEN latency_ms < 30000 THEN '<30s'
      WHEN latency_ms < 60000 THEN '30-60s'
      WHEN latency_ms < 120000 THEN '1-2min'
      WHEN latency_ms < 300000 THEN '2-5min'
      ELSE '>5min' END bucket, COUNT(*) n
    FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' AND latency_ms IS NOT NULL
    GROUP BY bucket`).all()
  // 功能模块维度（input JSON 的 feature/module 字段；SQLite 内置 json_extract）
  let byFeature = []
  let byModule = []
  try {
    byFeature = db.prepare(`
      SELECT json_extract(input,'$.feature') AS feature, COUNT(*) n, ROUND(AVG(latency_ms)) avg_ms
      FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' AND json_extract(input,'$.feature') IS NOT NULL
      GROUP BY feature ORDER BY n DESC LIMIT 10`).all()
    byModule = db.prepare(`
      SELECT json_extract(input,'$.module') AS module, COUNT(*) n
      FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' AND json_extract(input,'$.module') IS NOT NULL
      GROUP BY module ORDER BY n DESC`).all()
  } catch { /* json_extract 不可用时静默降级 */ }
  return {
    total, success, failed: total - success,
    successRate: total ? Math.round(100 * success / total) : 0,
    avgLatencyMs: one("SELECT ROUND(AVG(latency_ms)) v FROM runtime_agent_execution WHERE trigger_type LIKE 'auto:%' AND latency_ms IS NOT NULL").v ?? 0,
    tokenIn: tokens.i, tokenOut: tokens.o,
    conversations: one("SELECT COUNT(*) c FROM runtime_conversation WHERE data_origin='auto-simulated'").c,
    byTrigger, byTenant, byDay, tools, latencyBuckets, byFeature, byModule,
  }
}
