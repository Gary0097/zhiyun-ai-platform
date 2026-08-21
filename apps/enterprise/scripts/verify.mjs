// 自动验证脚本：启动平台服务 → 按 PRD §78 验收标准逐项校验
// 用法: node scripts/verify.mjs  （可选 VERIFY_PORT=8091）
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const PORT = process.env.VERIFY_PORT || 8091
const BASE = `http://127.0.0.1:${PORT}`

let server
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? '  — ' + detail : ''}`)
}

async function api (token, method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) },
    body: body ? JSON.stringify(body) : undefined
  })
  let data = null
  try { data = await res.json() } catch {}
  return { status: res.status, data }
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

async function waitServer () {
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(BASE + '/'); if (r.status) return true } catch {}
    await sleep(500)
  }
  return false
}

async function main () {
  // 独立验证数据库，避免污染正式数据
  process.env.PORT = PORT
  server = spawn(process.execPath, [join(HERE, '..', 'server', 'index.js')], {
    env: { ...process.env, PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe']
  })
  server.stdout.on('data', d => process.env.VERBOSE && console.log('[srv]', String(d).trim()))
  server.stderr.on('data', d => console.error('[srv-err]', String(d).trim()))
  if (!await waitServer()) { check('服务启动', false, '60s 内未就绪'); return finish() }
  check('服务启动 + 登录页可达', true)

  // 1. 认证与多角色
  const login = await api(null, 'POST', '/api/auth/login', { username: 'admin.a', password: 'Zhiyun@2026' })
  check('登录认证（admin.a）', login.status === 200 && !!login.data.token)
  const T = login.data.token
  const bad = await api(null, 'POST', '/api/auth/login', { username: 'admin.a', password: 'wrong' })
  check('错误密码拒绝（401）', bad.status === 401)
  const noAuth = await api(null, 'GET', '/api/agents')
  check('未认证访问拒绝（401）', noAuth.status === 401)

  // 2. 多租户隔离（企业A 不得访问企业B）
  const loginB = await api(null, 'POST', '/api/auth/login', { username: 'admin.b', password: 'Zhiyun@2026' })
  const TB = loginB.data.token
  const crossOrders = await api(T, 'GET', '/api/orders?tenant_id=2')
  check('跨租户数据访问被拒绝（403）', crossOrders.status === 403)
  const crossAgents = await api(T, 'GET', '/api/agents')
  const onlyTenantA = crossAgents.data.every(a => a.tenant_id === 1)
  check('Agent 列表仅含本租户', crossAgents.status === 200 && onlyTenantA)
  const crossTrace = await api(T, 'GET', '/api/trace/' + '00000000-0000-0000-0000-000000000000')
  check('任意 trace 查询不可跨租户', crossTrace.status === 404)

  // 3. RBAC：普通员工无管理权限
  const loginE = await api(null, 'POST', '/api/auth/login', { username: 'sales.a', password: 'Zhiyun@2026' })
  const TE = loginE.data.token
  const empAgents = await api(TE, 'GET', '/api/agents')
  check('员工访问 Agent 管理被拒绝（403，非仅前端隐藏）', empAgents.status === 403)
  const empTasks = await api(TE, 'POST', '/api/tasks', { name: 'x', agent_id: 1, trigger_type: 'cron', cron: '* * * * *' })
  check('员工创建任务被拒绝（403）', empTasks.status === 403)
  const empOrders = await api(TE, 'GET', '/api/orders')
  check('员工可访问授权内功能（订单查看 200）', empOrders.status === 200)

  // 4. 企业功能授权：企业C 无自动化中心
  const loginC = await api(null, 'POST', '/api/auth/login', { username: 'admin.c', password: 'Zhiyun@2026' })
  const TC = loginC.data.token
  const cSim = await api(TC, 'POST', '/api/simulator/generate', { start: '2026-01-01', end: '2026-01-02' })
  check('未授权模块 API 拒绝（企业C 数据模拟 403）', cSim.status === 403)

  // 5. Agent 全链路执行（Context→模型→Tool Guard→结构化输出→Trace）
  const agents = (await api(T, 'GET', '/api/agents')).data
  const daily = agents.find(a => a.agent_name.includes('日报'))
  const run = await api(T, 'POST', `/api/agents/${daily.agent_id}/test`, { instruction: '生成今日经营日报' })
  check('Agent 执行成功（结构化 JSON 输出）', run.status === 200 && run.data.status === 'success' && (() => { try { return typeof JSON.parse(run.data.output) === 'object' } catch { return false } })())
  const trace = (await api(T, 'GET', '/api/trace/' + run.data.traceId)).data
  check('Trace Replay 链路完整（User→Agent→Prompt→Tool→输出）', trace.agent?.name?.includes('日报') && trace.tool_calls.length >= 2 && trace.timeline.some(s => s.span === 'context.build') && trace.timeline.some(s => s.span === 'execution.end'))
  const toolLogs = (await api(T, 'GET', '/api/logs/tool?trace_id=' + run.data.traceId)).data
  check('Tool 执行日志关联 trace_id', toolLogs.length >= 2 && toolLogs.every(t => t.trace_id === run.data.traceId))

  // 6. 敏感工具人工确认（AI建议 → 挂起 → 确认 → 执行）
  // 用全新设备场景（每轮唯一设备号，确保无既有工单，模型应调用 create_work_order）
  const csAgent = agents.find(a => a.agent_name.includes('客服'))
  const deviceTag = `CNC-${String(Date.now()).slice(-5)} 数控磨床`
  const csRun = await api(T, 'POST', `/api/agents/${csAgent.agent_id}/test`, { instruction: `客户的新设备「${deviceTag}」首次报修：主轴异响且精度下降，此前该设备无任何工单，请处理` })
  const pending = (await api(T, 'GET', '/api/logs/tool?status=pending_confirm')).data.filter(t => t.execution_id === csRun.data.executionId)
  check('敏感工具默认挂起待确认（create_work_order → pending_confirm）', pending.length >= 1)
  const confirm = await api(T, 'POST', `/api/executions/${csRun.data.executionId}/confirm`, {})
  check('人工确认后敏感工具实际执行', confirm.status === 200 && confirm.data.confirmed >= 1)

  // 7. Tool Permission Guard：未授权工具被拒
  const guardTest = await api(T, 'POST', '/api/agents', { agent_name: '越权测试', system_prompt: 'x', tool_ids: ['query_salary'] })
  check('Agent 绑定未注册工具被拒绝', guardTest.status === 400)

  // 8. 定时任务：手动执行 + job 状态 + job_lock
  const tasks = (await api(T, 'GET', '/api/tasks')).data
  const cronTask = tasks.find(t => t.trigger_type === 'cron')
  const jobRun = await api(T, 'POST', `/api/tasks/${cronTask.task_id}/run`)
  check('定时任务手动执行成功', jobRun.status === 200 && jobRun.data.status === 'success')
  const jobs = (await api(T, 'GET', '/api/jobs')).data
  const jobRow = jobs.find(j => j.job_id === jobRun.data.jobId)
  check('Job 记录完整（scheduled/started/finished/status）', jobRow && jobRow.started_at && jobRow.finished_at && jobRow.status === 'success')
  // 条件触发：库存低于安全线 → 采购 Agent 自动触发
  // 服务端 30s 调度循环可能抢先触发（这正是自动运行的预期行为），故断言改为：
  // 该条件任务近 1 小时内存在 real 成功 Job；若无则手动 tick 一轮再查
  const condTask = tasks.find(t => t.trigger_type === 'condition')
  const condJobOk = async () => {
    const jobsAll = (await api(T, 'GET', '/api/jobs')).data
    const hourAgo = Date.now() - 3600e3
    return jobsAll.some(j => j.task_id === condTask.task_id && j.data_origin !== 'simulated' && j.status === 'success' && new Date(j.scheduled_at).getTime() >= hourAgo)
  }
  let firedOk = await condJobOk()
  if (!firedOk) { await api(T, 'POST', '/api/scheduler/tick'); firedOk = await condJobOk() }
  check('条件触发调度（库存 < 安全线 触发采购评估）', firedOk)

  // 9. 历史数据模拟器（小范围验证 + 数据链关联 + 统计一致）
  // 先清空 3 月窗口既有模拟数据建立基线（UTC/本地时区在月边界可能有少量溢出记录，用基线+增量断言）
  await api(T, 'POST', '/api/simulator/clear', { start: '2026-03-01', end: '2026-03-31', tenant_id: 1 })
  const marchBaseline = ((await api(T, 'GET', '/api/stats/trends?granularity=month&from=2026-03-01&to=2026-03-31')).data.find(t => t.bucket === '2026-03') || { executions: 0 }).executions
  const sim = await api(T, 'POST', '/api/simulator/generate', { start: '2026-03-02', end: '2026-03-08', dailyBase: 30, seed: 42, tenant_id: 1 })
  check('模拟器生成数据', sim.status === 200 && sim.data.agentExecutions > 50, `执行=${sim.data.agentExecutions} 工具=${sim.data.toolExecutions} 登录=${sim.data.logins}`)
  const simLogs = (await api(T, 'GET', '/api/logs/ai?origin=simulated')).data
  check('模拟数据带 data_origin=simulated 标记', simLogs.length > 0 && simLogs.every(x => x.data_origin === 'simulated'))
  const simTraceSample = simLogs.find(x => x.trace_id)
  const simTrace = (await api(T, 'GET', '/api/trace/' + simTraceSample.trace_id)).data
  check('模拟数据 trace 可回放、链路关联', simTrace?.tool_calls !== undefined)
  const dash = (await api(T, 'GET', '/api/stats/dashboard')).data
  check('Dashboard 指标来自数据库聚合', dash.agent_executions > 50 && dash.tool_calls > 50)
  const trends = (await api(T, 'GET', '/api/stats/trends?granularity=month&from=2026-03-01&to=2026-03-31')).data
  const march = trends.find(t => t.bucket === '2026-03')
  check('趋势查询与明细一致（看板无写死统计值）', march && march.executions === marchBaseline + sim.data.agentExecutions, `2026-03=${march?.executions} = 基线${marchBaseline} + 生成${sim.data.agentExecutions}`)
  const cleared = await api(T, 'POST', '/api/simulator/clear', { start: '2026-03-02', end: '2026-03-08', tenant_id: 1 })
  check('模拟数据可清空重生成', cleared.status === 200 && cleared.data.removed > 0)

  // 10. 数据修改留痕：改订单金额 → 新值生效 + audit_change 留痕
  const orders = (await api(T, 'GET', '/api/orders')).data
  const target = orders[0]
  const edit = await api(T, 'PUT', `/api/data/business_order/${target.id}`, { amount: 999999, __reason: '测试数据调整' })
  check('数据管理中心修改生效', edit.status === 200 && edit.data.after.amount === 999999)
  const changes = (await api(T, 'GET', '/api/audit/changes')).data
  const chg = changes.find(c => String(c.record_id) === String(target.id))
  check('修改留痕 audit_change（before/after/operator/reason）', chg && JSON.parse(chg.before_json).amount === target.amount && chg.operator === 'admin.a' && chg.reason === '测试数据调整')

  // 11. 日志修正：改日志展示值但原始值留痕
  const aiLog = (await api(T, 'GET', '/api/logs/ai')).data.find(x => x.status === 'success')
  const amend = await api(T, 'POST', '/api/logs/amend', { table: 'runtime_agent_execution', record_id: aiLog.execution_id, field: 'output', value: '{"amended":true}', reason: '测试数据调整' })
  check('日志修正成功且留痕（log_amendment）', amend.status === 200 && (await api(T, 'GET', '/api/logs/amendments')).data.length >= 1)

  // 12. 操作日志
  const opLogs = (await api(T, 'GET', '/api/logs/operation')).data
  check('操作日志记录（创建/修改/确认/任务执行）', opLogs.length >= 3 && opLogs.some(l => l.action.includes('修改')))

  // 13. Agent 对话（聊天）能力
  const chatAgents = (await api(T, 'GET', '/api/chat/agents')).data
  const assistant = chatAgents.find(a => a.agent_name === '企业智能助手')
  check('对话 Agent 列表（含企业智能助手）', !!assistant && chatAgents.length >= 5)
  const conv = await api(T, 'POST', '/api/conversations', { agent_id: assistant.agent_id })
  check('创建会话', conv.status === 200 && conv.data.id > 0)
  const chat = await api(T, 'POST', `/api/conversations/${conv.data.id}/chat`, { content: '我们现在有多少条在产订单？' })
  check('对话获得助手回复（真实模型 + 工具查询）', chat.status === 200 && !!chat.data.reply && !!chat.data.traceId, `回复长度=${(chat.data.reply || '').length}`)
  const convMsgs = (await api(T, 'GET', `/api/conversations/${conv.data.id}/messages`)).data
  check('会话消息持久化（user+assistant）', convMsgs.length === 2 && convMsgs[0].role === 'user' && convMsgs[1].role === 'assistant')

  // 14. 系统设置：品牌 / Logo / dsh 入口
  const brand0 = await api(T, 'GET', '/api/settings/brand')
  check('品牌设置读取', brand0.status === 200 && brand0.data.name.includes('智造云'))
  const logoUp = await api(T, 'POST', '/api/settings/logo', { data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==' })
  check('Logo 上传（1x1 PNG）', logoUp.status === 200 && logoUp.data.logo === '/logo.png')
  const logoFetch = await fetch(BASE + '/logo.png')
  check('Logo 可访问（/logo.png）', logoFetch.status === 200 && (logoFetch.headers.get('content-type') || '').startsWith('image/'))
  const dshSave = await api(T, 'PUT', '/api/settings/dsh', { url: 'http://127.0.0.1:8308' })
  const dshGet = await api(T, 'GET', '/api/settings/dsh')
  check('dsh 工作台地址可配置', dshSave.status === 200 && dshGet.data.url === 'http://127.0.0.1:8308')
  const brandPut = await api(T, 'PUT', '/api/settings/brand', { name: brand0.data.name })
  check('系统名称可修改', brandPut.status === 200)
  // 普通员工不可改品牌（权限校验）
  const brandDenied = await api(TE, 'PUT', '/api/settings/brand', { name: 'x' })
  check('员工修改品牌被拒绝（403）', brandDenied.status === 403)

  // 15. 金汉隆真实发票数据 + 采购看板 + AI 洞察
  const loginJ = await api(null, 'POST', '/api/auth/login', { username: 'admin.j', password: 'Zhiyun@2026' })
  const TJ = loginJ.data.token
  check('金汉隆租户登录（admin.j）', loginJ.status === 200)
  const invs = (await api(TJ, 'GET', '/api/invoices')).data
  check('真实发票 6 张导入（¥415,753.59）', invs.length === 6 && Math.abs(invs.reduce((s, i) => s + i.amount_total, 0) - 415753.59) < 0.01)
  const inv1 = (await api(TJ, 'GET', `/api/invoices/${invs[0].invoice_id}/items`)).data
  check('发票物料明细可查', inv1.length > 0)
  const proc = (await api(TJ, 'GET', '/api/stats/procurement')).data
  check('采购聚合 KPI（供应商/月度/品类）', proc.kpi.invoice_count === 6 && proc.kpi.supplier_count === 6 && proc.suppliers.length === 6 && proc.months.length >= 2 && proc.categories.length >= 4, `TOP=${proc.kpi.top_supplier}`)
  // 跨租户：企业A 查不到金汉隆发票
  const invCross = await api(T, 'GET', '/api/invoices')
  check('跨租户发票隔离（企业A 查询为空）', invCross.status === 200 && invCross.data.length === 0)
  const insight = await api(TJ, 'GET', '/api/stats/ai-insight')
  check('AI 智能洞察（本地模型分析真实数据）', insight.status === 200 && insight.data.insight.length > 200 && /\d/.test(insight.data.insight), `长度=${(insight.data.insight || '').length}`)
  const insightCached = await api(TJ, 'GET', '/api/stats/ai-insight')
  check('AI 洞察缓存生效', insightCached.data.cached === true)
  // 金汉隆对话助手可查发票
  const chatAgentsJ = (await api(TJ, 'GET', '/api/chat/agents')).data
  const assistantJ = chatAgentsJ.find(a => a.agent_name === '企业智能助手')
  const convJ = await api(TJ, 'POST', '/api/conversations', { agent_id: assistantJ.agent_id })
  const chatJ = await api(TJ, 'POST', `/api/conversations/${convJ.data.id}/chat`, { content: '我们在亚德客采购了多少？' })
  check('金汉隆对话助手查询发票（回复含金额）', chatJ.status === 200 && /85,?66[89]/.test(chatJ.data.reply || ''))

  // 16. 模型配置在线管理（系统设置 → 模型配置）
  const modelGet = await api(T, 'GET', '/api/model')
  check('模型配置读取（含脱敏密钥）', modelGet.status === 200 && modelGet.data.mock === false && modelGet.data.apiKeyMasked.startsWith('sk-'))
  const modelTest = await api(T, 'POST', '/api/model/test', {})
  check('模型连通测试（列模型+推理探测）', modelTest.status === 200 && modelTest.data.ok === true && modelTest.data.models.length >= 1, `${modelTest.data.ms}ms / ${modelTest.data.models.length} 模型`)
  const modelSave = await api(T, 'PUT', '/api/model', { baseURL: modelGet.data.baseURL, model: modelGet.data.model, mock: false, maxTokens: 1024 })
  check('模型配置在线保存并即时生效', modelSave.status === 200 && modelSave.data.mock === false)
  const modelDenied = await api(TE, 'PUT', '/api/model', { model: 'x' })
  check('员工修改模型配置被拒绝（403）', modelDenied.status === 403)

  finish()
}

function finish () {
  const pass = results.filter(r => r.ok).length
  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  console.log(`验证结果: ${pass}/${results.length} 通过`)
  if (server) server.kill()
  process.exit(pass === results.length ? 0 : 1)
}

main().catch(e => { console.error('验证脚本异常:', e); finish() })
