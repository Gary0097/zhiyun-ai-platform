// Model Adapter：业务代码禁止直连模型 API，统一经本适配层（PRD §75）
// OpenAI 兼容 chat/completions；未配置端点时自动进入 mock 模式（确定性结构化输出，用于离线验证全链路）
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const cfgPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'config', 'model.json')

let runtimeOverride = null

/** 管理端在线修改模型配置（写入 config/model.json 并即时生效，无需重启） */
export function updateModelConfig (patch) {
  const current = loadModelConfig()
  const next = { ...current }
  for (const k of ['mock', 'provider', 'baseURL', 'apiKeyEnv', 'apiKey', 'model', 'api', 'maxTokens', 'disableThinking', 'temperature', 'timeoutMs']) {
    if (patch[k] !== undefined) next[k] = patch[k]
  }
  writeFileSync(cfgPath, JSON.stringify(next, null, 2) + '\n')
  runtimeOverride = null
  return modelInfo()
}

export function loadModelConfig () {
  if (runtimeOverride) return runtimeOverride
  if (!existsSync(cfgPath)) return { mock: true, provider: 'mock', baseURL: '', apiKeyEnv: '', model: 'mock-structured', api: 'openai-completions' }
  return JSON.parse(readFileSync(cfgPath, 'utf8'))
}

export function resolveApiKey (cfg) {
  if (!cfg.apiKeyEnv) return cfg.apiKey || ''
  return process.env[cfg.apiKeyEnv] || cfg.apiKey || ''
}

async function callOpenAI (cfg, messages, tools, userHint) {
  const key = resolveApiKey(cfg)
  if (!key) throw new Error(`模型凭据缺失：请设置环境变量 ${cfg.apiKeyEnv} 或在 config/model.json 填写 apiKey`)
  const body = { model: cfg.model, messages, temperature: cfg.temperature ?? 0.3, max_tokens: cfg.maxTokens ?? 1024 }
  // 本地 Qwen3 系推理模型：关闭思考模式可避免无限推理导致超时（可通过配置覆盖）
  if (cfg.disableThinking !== false) body.chat_template_kwargs = { enable_thinking: false }
  if (tools?.length) {
    body.tools = tools.map(t => ({ type: 'function', function: { name: t.name, description: t.description, parameters: t.schema } }))
    body.tool_choice = 'auto'
  }
  const res = await fetch(cfg.baseURL.replace(/\/$/, '') + '/chat/completions', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(cfg.timeoutMs ?? 300000)
  })
  if (!res.ok) throw new Error(`模型端点错误 ${res.status}: ${(await res.text()).slice(0, 300)}`)
  const data = await res.json()
  const choice = data.choices?.[0]?.message || {}
  const toolCalls = (choice.tool_calls || []).map(tc => ({ name: tc.function.name, args: safeParse(tc.function.arguments) }))
  return {
    content: choice.content || '',
    toolCalls,
    tokenInput: data.usage?.prompt_tokens || 0,
    tokenOutput: data.usage?.completion_tokens || 0
  }
}

function safeParse (s) { try { return JSON.parse(s) } catch { return {} } }

/** mock 模式：按 system prompt 中的输出契约生成确定性的工具调用序列与结构化输出 */
async function callMock (cfg, messages, tools) {
  const system = messages.find(m => m.role === 'system')?.content || ''
  const lastUser = [...messages].reverse().find(m => m.role === 'user')?.content || ''
  const tokenIn = Math.round((system.length + lastUser.length) / 3) + 120
  // 第一步：调用全部可用业务工具采集数据；后续步骤直接产出最终结构化结果
  const toolResults = messages.filter(m => m.role === 'tool')
  if (tools?.length && toolResults.length === 0) {
    return { content: '', toolCalls: tools.map(t => ({ name: t.name, args: t.mockArgs || {} })), tokenInput: tokenIn, tokenOutput: 48 }
  }
  const jsonHint = system.match(/\{[^]*?\}/)
  let out = '{}'
  if (/日报/.test(system)) {
    out = { metrics: { new_orders: 3, done_orders: 1, delayed_orders: 1, sales_amount: 1268000, receivable: 1260000, after_sale_open: 1 }, summary: '（mock）今日订单平稳，SO-2026-1004 延迟需关注，应收余额偏高。' }
  } else if (/风险/.test(system)) {
    out = { risk_score: 78, risk_level: '红色', risk_reason: ['生产进度落后计划 36 小时', '关键物料库存低于安全线'], expected_delay_hours: 48, suggestion: '联系生产负责人确认排期并启动补货评估' }
  } else if (/采购|补货/.test(system)) {
    out = { items: [{ material: 'SKF 轴承 6208', suggest_qty: 180, suggest_supplier: 'SKF 中国', risk_level: '黄色' }], reason: '（mock）库存 60 低于安全库存 120，按 7 天消耗建议补货。' }
  } else if (/客服|售后/.test(system)) {
    out = { intent: '售后故障', device_match: 'CNC-加工中心 VMC850', similar_cases: ['2026-05 主轴异响-更换轴承解决'], advice: '建议先检测主轴轴承磨损，安排工程师上门', create_work_order: true }
  } else if (/财务/.test(system)) {
    out = { income: 5820000, expense: 3980000, receivable: 1260000, payable: 0, trend: '上涨', analysis: '（mock）收入环比上升，应收回款正常。' }
  } else {
    out = { orders: [{ order_no: 'SO-2026-1001', current_node: '生产', progress: 45, delay_hours: 0, risk_level: '黄色' }], summary: '（mock）在产订单整体受控。' }
  }
  const content = JSON.stringify(out)
  return { content, toolCalls: [], tokenInput: tokenIn, tokenOutput: Math.round(content.length / 3) + 60 }
}

/** 统一模型调用入口：返回 {content, toolCalls, tokenInput, tokenOutput} */
export async function chat (messages, tools = []) {
  const cfg = loadModelConfig()
  if (cfg.mock) return callMock(cfg, messages, tools)
  return callOpenAI(cfg, messages, tools, '')
}

export const modelInfo = () => {
  const cfg = loadModelConfig()
  return {
    mock: !!cfg.mock, provider: cfg.provider || 'custom', baseURL: cfg.baseURL, model: cfg.model,
    apiKeyEnv: cfg.apiKeyEnv || '', api: cfg.api || 'openai-completions',
    maxTokens: cfg.maxTokens ?? 1024, disableThinking: cfg.disableThinking !== false,
    // 密钥只回脱敏描述
    apiKeyMasked: resolveApiKey(cfg) ? String(resolveApiKey(cfg)).slice(0, 7) + '****' : ''
  }
}

/** 连通性测试：列模型 + 一次极小补全，返回诊断信息 */
export async function testModelConnection (cfgOverride = null) {
  const cfg = cfgOverride || loadModelConfig()
  const t0 = Date.now()
  const out = { ok: false, ms: 0, baseURL: cfg.baseURL, model: cfg.model, models: [], error: '' }
  try {
    const key = resolveApiKey(cfg)
    const res = await fetch(cfg.baseURL.replace(/\/$/, '') + '/models', { headers: { authorization: 'Bearer ' + key }, signal: AbortSignal.timeout(15000) })
    out.ms = Date.now() - t0
    if (!res.ok) { out.error = `GET /models ${res.status}`; return out }
    const data = await res.json()
    out.models = (data.data || []).map(m => m.id).slice(0, 30)
    // 探测一次 1-token 补全验证推理可用
    const r2 = await fetch(cfg.baseURL.replace(/\/$/, '') + '/chat/completions', {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + key },
      body: JSON.stringify({ model: cfg.model, messages: [{ role: 'user', content: 'hi' }], max_tokens: 1, chat_template_kwargs: { enable_thinking: false } }),
      signal: AbortSignal.timeout(60000)
    })
    if (!r2.ok) { out.error = `chat/completions ${r2.status}: ${(await r2.text()).slice(0, 120)}`; return out }
    out.ok = true
  } catch (e) { out.ms = Date.now() - t0; out.error = e.message }
  return out
}
