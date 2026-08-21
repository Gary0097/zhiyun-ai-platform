// 知识收割器（Knowledge Harvester）
// 链路：联网检索资料（web-research.md，已落地工作区）→ Qwen27B 通过 dsh 会话阅读加工
// → 生成结构化知识条目（JSON）→ 解析灌入 business_knowledge_item → 导出 KNOWLEDGE.md
// 到工作区供 dsh 会话直接阅读（DSH 调用链路）。执行记录落库 trigger_type='auto:research'。
import { db, DATA_DIR } from './db.js'
import { randomUUID } from 'node:crypto'
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const ORIGIN = 'web-research'
const trace = msg => console.error(`[harvest ${new Date().toISOString().replace('T', ' ').slice(0, 19)}] ${msg}`)
const now = () => new Date().toISOString().replace('T', ' ').slice(0, 19)
const sleep = ms => new Promise(r => setTimeout(r, ms))

function dshBase () {
  return (db.prepare("SELECT value FROM business_setting WHERE key = 'dsh.url'").get()?.value || 'http://127.0.0.1:8308').replace(/\/+$/, '')
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
// 与 auto-run.js 相同的会话/轮次原语（独立实现避免循环依赖）
// ---------------------------------------------------------------------------

const activeSessions = new Set()

async function ensureSession (tenantId, roleKey) {
  const code = db.prepare('SELECT code FROM business_tenant WHERE id = ?').get(tenantId)?.code
  const dir = join(DATA_DIR, 'workspaces', code)
  mkdirSync(dir, { recursive: true })
  const wsList = await rpc('workspace.list', {})
  let ws = (wsList.items ?? []).find(w => w.path === dir)
  if (!ws) ws = await rpc('workspace.create', { path: dir })
  const key = `auto.session.${tenantId}.${roleKey}`
  const saved = db.prepare('SELECT value FROM business_setting WHERE key = ?').get(key)?.value
  if (saved) {
    try { await rpc('session.create', { sessionId: saved, workspaceId: ws.workspaceId }); return saved } catch { /* 失效重建 */ }
  }
  const sessionId = `session-${randomUUID()}`
  await rpc('session.create', { sessionId, workspaceId: ws.workspaceId })
  db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at')
    .run(key, sessionId, now())
  return sessionId
}

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

async function runTurn (sessionId, text, timeoutMs = 600_000) {
  const startedAt = Date.now()
  const tail = await rpc('session.history', { sessionId, maxMessages: 1 })
  let baseline = -1
  for (const e of tail.events ?? []) baseline = Math.max(baseline, e.event.seq)
  await rpc('session.prompt', { sessionId, mode: 'queue', content: [{ type: 'text', text }] })
  const deadline = startedAt + timeoutMs
  while (Date.now() < deadline) {
    await sleep(3_000)
    const page = await rpc('session.history', { sessionId, maxMessages: 20 })
    const fresh = (page.events ?? []).filter(e => e.event.seq > baseline)
    const end = fresh.find(e => e.event.type === 'turn/end')
    if (end) return { ok: true, text: extractAssistantText(fresh), latencyMs: Date.now() - startedAt }
  }
  await rpc('session.cancel', { sessionId }).catch(() => {})
  throw new Error('收割轮次超时')
}

/** 审批/问题自动应答（与 auto-run 相同机制，监听自有会话集） */
let harvestMux = null
function startHarvestListener () {
  if (harvestMux) return
  harvestMux = new AbortController()
  const { signal } = harvestMux
  const wsUrl = dshBase().replace(/^http/, 'ws') + '/api/events.mux'
  const respond = async (rpcId, value) => {
    await fetch(`${dshBase()}/api/respond`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ type: 'client-response', rpcId, result: { ok: true, value } }),
      signal: AbortSignal.timeout(10_000),
    }).catch(() => null)
  }
  const loop = async () => {
    while (!signal.aborted) {
      await new Promise(resolve => {
        const ws = new WebSocket(wsUrl)
        const onAbort = () => { try { ws.close() } catch {} resolve() }
        signal.addEventListener('abort', onAbort, { once: true })
        ws.onmessage = ev => {
          try {
            const frame = JSON.parse(String(ev.data))
            if (frame?.type !== 'server-request' || !activeSessions.has(frame.payload?.sessionId)) return
            const p = frame.payload
            if (frame.method === 'approval/requested') void respond(frame.rpcId, { sessionId: p.sessionId, approvalId: p.approvalId, outcome: 'allowed-once' })
            else if (frame.method === 'question/requested') void respond(frame.rpcId, {
              sessionId: p.sessionId,
              answer: { answers: (p.questions ?? []).map(q => ({ id: q.id, selected: q.options?.length ? [q.options[0].label] : [], custom: '请基于已有资料直接继续。' })) },
            })
          } catch { /* 忽略坏帧 */ }
        }
        ws.onclose = () => { signal.removeEventListener('abort', onAbort); resolve() }
        ws.onerror = () => { signal.removeEventListener('abort', onAbort); resolve() }
      })
      if (signal.aborted) return
      await sleep(3_000)
    }
  }
  loop().catch(() => {})
}

// ---------------------------------------------------------------------------
// 知识库操作
// ---------------------------------------------------------------------------

function ensureKnowledgeBase (tenantId) {
  const key = 'research.kb.id'
  const saved = db.prepare('SELECT value FROM business_setting WHERE key = ?').get(key)?.value
  if (saved && db.prepare('SELECT id FROM business_knowledge WHERE id = ?').get(Number(saved))) return Number(saved)
  const kb = db.prepare("SELECT id FROM business_knowledge WHERE tenant_id = ? AND name = '企业联网资料库'").get(tenantId)
  if (kb) { db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(key, String(kb.id), now()); return kb.id }
  const id = db.prepare('INSERT INTO business_knowledge (tenant_id, name, description, status, created_by, created_at, data_origin) VALUES (?,?,?,?,null,?,?)')
    .run(tenantId, '企业联网资料库', 'AI 联网检索公开渠道整理的企业资料（工商/产品/客户/市场），由 Qwen27B 自动加工', 'active', now(), ORIGIN).lastInsertRowid
  db.prepare('INSERT INTO business_setting (key, value, updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(key, String(id), now())
  return Number(id)
}

function insertItem (kbId, tenantId, title, content, tags) {
  db.prepare('INSERT INTO business_knowledge_item (knowledge_id, tenant_id, title, content, tags, created_by, created_at, data_origin) VALUES (?,?,?,?,?,null,?,?)')
    .run(kbId, tenantId, title, content, tags, now(), ORIGIN)
}

/** 导出全部知识条目为工作区 KNOWLEDGE.md（dsh 会话可直接阅读 = DSH 调用知识库） */
export function exportKnowledgeDoc (tenantId) {
  const code = db.prepare('SELECT code FROM business_tenant WHERE id = ?').get(tenantId)?.code
  if (!code) return 0
  const rows = db.prepare(`
    SELECT k.name AS kb, i.title, i.content, i.tags FROM business_knowledge_item i
    JOIN business_knowledge k ON k.id = i.knowledge_id WHERE i.tenant_id = ? ORDER BY k.id, i.id`).all(tenantId)
  const dir = join(DATA_DIR, 'workspaces', code)
  mkdirSync(dir, { recursive: true })
  let cur = ''
  const parts = ['# 企业知识库导出（KNOWLEDGE.md）', '', `> 共 ${rows.length} 条知识条目，由平台自动导出（${now()}）。dsh 会话回答企业问题时应优先阅读本文件。`, '']
  for (const r of rows) {
    if (r.kb !== cur) { cur = r.kb; parts.push(`## 知识库：${cur}`, '') }
    parts.push(`### ${r.title}${r.tags ? `（${r.tags}）` : ''}`, '', r.content, '')
  }
  writeFileSync(join(dir, 'KNOWLEDGE.md'), parts.join('\n'), 'utf8')
  // FUNCTIONS.md 提示知识库存在
  const fx = join(dir, 'FUNCTIONS.md')
  if (existsSync(fx)) {
    let doc = readFileSync(fx, 'utf8')
    if (!doc.includes('KNOWLEDGE.md')) doc += '\n## 企业知识库\n详见工作区内 `KNOWLEDGE.md`（全部知识条目导出，含设备维修、管理制度与企业联网资料）。回答企业问题时应优先检索。\n'
    writeFileSync(fx, doc, 'utf8')
  }
  return rows.length
}

// ---------------------------------------------------------------------------
// 主流程：Qwen27B 阅读资料 → 生成条目 JSON → 灌库
// ---------------------------------------------------------------------------

const HARVEST_PLAN = [
  { topic: '企业工商与资质', prompt: '阅读工作区 web-research.md 的「工商注册信息」与「企业定位与产品体系」章节，输出 6-8 条企业基本信息知识条目（成立时间/注册资本/法定代表人/资质荣誉/经营范围/企业定位/三大产品板块等，每条一个主题）。' },
  { topic: '产品体系与应用', prompt: '阅读工作区 web-research.md 的「企业定位与产品体系」章节，输出 6-8 条产品知识条目（每条覆盖一条产品线：枕式/立式/理料线/茶叶/给袋式/装盒装箱/液体粉末机型，含典型参数与应用行业）。' },
  { topic: '客户市场与外贸', prompt: '阅读工作区 web-research.md 的「客户与市场」「技术团队」「企业文化与管理」章节，输出 5-7 条市场与经营知识条目（合作品牌/出口市场/电商渠道布局/推广投入/团队规模/招聘方向/企业文化）。' },
  { topic: '行业知识衍生', prompt: '基于工作区 web-research.md 中金汉隆的产品应用行业（食品/药品/日化包装），输出 4-6 条行业应用知识条目（如食品包装机选型要点/药品装盒机参数要求/给袋式与预制袋方案对比/理料线规划），条目内容须与资料中的真实参数呼应。' },
]

const H = { running: false, lastRun: null, items: 0, error: null }

export function harvestStatus () {
  return { ...H, plan: HARVEST_PLAN.map(p => p.topic) }
}

/**
 * 执行一轮知识收割（幂等：每轮跳过已存在的同名条目标题）。
 * @param {object} user 触发者（用于日志归属，可传系统用户）
 */
export async function runKnowledgeHarvest (user = null) {
  if (H.running) return { ok: false, message: '收割进行中' }
  H.running = true; H.error = null
  const jhl = db.prepare("SELECT id, code, name FROM business_tenant WHERE code = 'jhl'").get()
  if (!jhl) { H.running = false; throw new Error('金汉隆租户不存在') }
  const researchFile = join(DATA_DIR, 'workspaces', jhl.code, 'web-research.md')
  if (!existsSync(researchFile)) { H.running = false; throw new Error('web-research.md 不存在') }
  const kbId = ensureKnowledgeBase(jhl.id)
  let sessionId = null
  let totalItems = 0
  try {
    sessionId = await ensureSession(jhl.id, 'research')
    activeSessions.add(sessionId)
    startHarvestListener()
    trace(`知识收割启动（${HARVEST_PLAN.length} 个主题，会话 ${sessionId.slice(0, 20)}…）`)
    for (const plan of HARVEST_PLAN) {
      const question = `${plan.prompt}\n\n严格输出 JSON 数组（不要 markdown 代码块，不要其他文字）：[{"title":"条目标题","content":"条目正文（100-300字，自包含、可供检索）","tags":"分类标签"}]`
      try {
        const turn = await runTurn(sessionId, question)
        const raw = turn.text.replace(/^```(json)?/m, '').replace(/```$/m, '').trim()
        const m = raw.match(/\[[\s\S]*\]/)
        const items = m ? JSON.parse(m[0]) : []
        let added = 0
        for (const it of items) {
          if (!it?.title || !it?.content) continue
          const exists = db.prepare('SELECT 1 FROM business_knowledge_item WHERE knowledge_id = ? AND title = ?').get(kbId, String(it.title))
          if (exists) continue
          insertItem(kbId, jhl.id, String(it.title), String(it.content), it.tags ? String(it.tags) : plan.topic)
          added++
        }
        totalItems += added
        trace(`主题「${plan.topic}」: ${items.length} 条生成 / ${added} 条新增（${turn.latencyMs}ms）`)
        // 收割轮次也落执行日志（复用 auto-run 的表结构）
        logResearchRound(jhl, plan.topic, question, turn, added)
      } catch (e) {
        trace(`主题「${plan.topic}」失败: ${e.message}`)
        logResearchRound(jhl, plan.topic, question, null, 0, e.message)
      }
    }
    // 导出 KNOWLEDGE.md（DSH 调用链路）
    const exported = exportKnowledgeDoc(jhl.id)
    H.lastRun = now(); H.items = totalItems
    trace(`收割完成: 新增 ${totalItems} 条，知识库导出 ${exported} 条 → KNOWLEDGE.md`)
    return { ok: true, added: totalItems, exported }
  } catch (e) {
    H.error = e.message
    trace(`收割失败: ${e.message}`)
    throw e
  } finally {
    H.running = false
    if (sessionId) activeSessions.delete(sessionId)
    if (activeSessions.size === 0) { if (harvestMux) { harvestMux.abort(); harvestMux = null } }
  }
}

function logResearchRound (tenant, topic, question, turn, added, error = null) {
  const t = now()
  db.prepare(`INSERT INTO runtime_agent_execution (trace_id, tenant_id, user_id, agent_id, trigger_type, input, output, status, started_at, finished_at, latency_ms, model, token_input, token_output, error, data_origin)
    VALUES (?,?,null,null,?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(randomUUID(), tenant.id, 'auto:research',
      JSON.stringify({ instruction: question.slice(0, 500), role: '企业资料研究员', feature: '企业资料联网收割', module: '知识库' }),
      error ? null : `新增知识条目 ${added} 条`, error ? 'failed' : 'success', t, now(),
      turn?.latencyMs ?? null, 'Qwen3.8-27B · dsh Harness',
      Math.ceil(question.length / 3), Math.ceil((turn?.text?.length ?? 0) / 3), error, ORIGIN)
}
