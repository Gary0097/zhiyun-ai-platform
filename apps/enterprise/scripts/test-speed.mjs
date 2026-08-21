// 测试限流参数：max_tokens 与 Qwen3 关闭思考
const MODEL = 'DavidAU/Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-MTP-GGUF'
const KEY = 'sk-unsloth-a9f6384841cccb1d3ea95f1caf78c9a0'

const sys = `# 角色与任务
你是企业经营日报专家。汇总当日订单、销售、应收与售后数据生成日报。必须输出 JSON：{"metrics":{"new_orders":0,"done_orders":0,"delayed_orders":0,"sales_amount":0,"receivable":0,"after_sale_open":0},"summary":""}
# 可用工具
query_order、query_finance、query_after_sale。业务数据必须通过工具获取，不得凭空编造。
# 输出要求
最终回复必须是符合系统提示词约定的单个 JSON 对象，不要输出多余文本。`

const tools = ['query_order', 'query_finance', 'query_after_sale'].map(n => ({
  type: 'function', function: { name: n, description: '查询数据', parameters: { type: 'object', properties: {} } }
}))

const variants = [
  { name: 'max_tokens=512', extra: { max_tokens: 512 } },
  { name: '关思考(chat_template_kwargs)', extra: { max_tokens: 800, chat_template_kwargs: { enable_thinking: false } } },
  { name: '关思考(reasoning_effort)', extra: { max_tokens: 800, reasoning_effort: 'none' } }
]

for (const v of variants) {
  const t0 = Date.now()
  try {
    const res = await fetch('http://127.0.0.1:8888/v1/chat/completions', {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + KEY },
      body: JSON.stringify({ model: MODEL, temperature: 0.3, messages: [{ role: 'system', content: sys }, { role: 'user', content: '生成今日经营日报' }], tools, tool_choice: 'auto', ...v.extra }),
      signal: AbortSignal.timeout(300000)
    })
    const d = await res.json()
    const m = d.choices?.[0]?.message
    console.log(`【${v.name}】${res.status} ${((Date.now() - t0) / 1000).toFixed(1)}s`)
    console.log('  tool_calls:', m?.tool_calls ? m.tool_calls.map(t => t.function.name).join(',') : '无')
    console.log('  content:', JSON.stringify(m?.content)?.slice(0, 150))
    console.log('  reasoning长:', (m?.reasoning_content || '').length)
  } catch (e) {
    console.log(`【${v.name}】失败 ${((Date.now() - t0) / 1000).toFixed(1)}s ${e.message}`)
  }
}
