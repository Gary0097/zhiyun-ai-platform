// 网关连通性测试：chat + tool calling
const MODEL = 'DavidAU/Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-MTP-GGUF'
const BASE = 'http://127.0.0.1:8888/v1'
const KEY = 'sk-unsloth-a9f6384841cccb1d3ea95f1caf78c9a0'

const call = async (body) => {
  const t0 = Date.now()
  const res = await fetch(BASE + '/chat/completions', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + KEY },
    body: JSON.stringify(body)
  })
  const d = await res.json()
  return { status: res.status, ms: Date.now() - t0, d }
}

const main = async () => {
  // 1. 纯文本
  let r = await call({ model: MODEL, temperature: 0.3, max_tokens: 300, messages: [
    { role: 'system', content: '你是订单监控专家，必须只输出 JSON：{"summary":"..."}' },
    { role: 'user', content: '总结：3个订单中1个延迟36小时' }
  ]})
  console.log('【文本】', r.status, r.ms + 'ms')
  console.log('  输出:', JSON.stringify(r.d.choices?.[0]?.message?.content)?.slice(0, 200))
  console.log('  usage:', JSON.stringify(r.d.usage))
  if (r.d.choices?.[0]?.message?.reasoning_content) console.log('  (含 reasoning_content 字段)')

  // 2. Tool calling
  r = await call({ model: MODEL, temperature: 0.3, max_tokens: 300, messages: [
    { role: 'system', content: '你是采购专家，通过工具查询库存。' },
    { role: 'user', content: '查一下轴承库存' }
  ], tools: [{ type: 'function', function: { name: 'query_inventory', description: '查询库存', parameters: { type: 'object', properties: { material: { type: 'string' } } } } }], tool_choice: 'auto' })
  const msg = r.d.choices?.[0]?.message
  console.log('【工具】', r.status, r.ms + 'ms')
  console.log('  tool_calls:', JSON.stringify(msg?.tool_calls)?.slice(0, 300))
  console.log('  content:', JSON.stringify(msg?.content)?.slice(0, 120))
}
main().catch(e => { console.error('失败:', e.message); process.exit(1) })
