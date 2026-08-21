// 验证 dsh 新模型配置：新建会话提问，检查 session.models 当前模型
const BASE = 'http://127.0.0.1:8308'
const rpc = async (method, payload, timeoutMs = 120_000) => {
  const res = await fetch(`${BASE}/api/${method}`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method, payload }),
    signal: AbortSignal.timeout(timeoutMs),
  })
  const body = await res.json()
  if (!body?.result?.ok) throw new Error(method + ': ' + JSON.stringify(body?.result?.error ?? 'no result'))
  return body.result.value
}
const sleep = ms => new Promise(r => setTimeout(r, ms))

// 1. 新会话（不传 workspaceId，走默认 cwd）
const sid = `session-${crypto.randomUUID()}`
await rpc('session.create', { sessionId: sid })
console.log('会话已创建:', sid.slice(0, 24) + '…')

// 2. 查会话当前模型
const models = await rpc('session.models', { sessionId: sid })
console.log('当前模型:', models.current.provider, '/', models.current.model)
console.log('可路由分组:', models.groups.map(g => `${g.id}(${g.models.map(m => m.id).join(',')})`).join(' | ') || '（空）')
console.log('加载失败:', models.failures.map(f => `${f.id}:${f.message}`).join(' | ') || '无')

// 3. 发一个问题验证真实响应
const tail = await rpc('session.history', { sessionId: sid, maxMessages: 1 })
let baseline = -1
for (const e of tail.events ?? []) baseline = Math.max(baseline, e.event.seq)
await rpc('session.prompt', { sessionId: sid, mode: 'queue', content: [{ type: 'text', text: '你好，请用一句话确认你是哪个模型。' }] })
for (let i = 0; i < 30; i++) {
  await sleep(3_000)
  const page = await rpc('session.history', { sessionId: sid, maxMessages: 20 })
  const fresh = (page.events ?? []).filter(e => e.event.seq > baseline)
  if (fresh.find(e => e.event.type === 'turn/end')) {
    let text = ''
    for (const { event } of fresh) {
      if (event.type !== 'assistant/message') continue
      const c = event.data?.message?.content
      if (Array.isArray(c)) { const t = c.filter(b => b?.type === 'text').map(b => b.text).join(''); if (t) text = t }
    }
    console.log('--- 模型回复 ---')
    console.log(text.slice(0, 300))
    process.exit(0)
  }
}
console.log('超时')
