// 验证 DSH 知识库调用链路：向 jhl 工作区会话提问，模型应阅读 KNOWLEDGE.md 作答
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

// 找 jhl 工作区的 feature-demo 会话（知识收割/演示共用）
const ws = await rpc('workspace.list', {})
const jhl = (ws.items ?? []).find(w => w.path.includes('jhl'))
const sessions = await rpc('session.list', {})
// 用会话的 cwd 判断
let target = null
for (const s of sessions.items ?? []) {
  if (s.cwd?.includes('jhl')) { target = s.sessionId; if (!s.running) break }
}
if (!target) throw new Error('未找到 jhl 会话')
console.log('目标会话:', target.slice(0, 24) + '…')

const q = '请阅读工作区中的 KNOWLEDGE.md 回答：金汉隆公司什么时候成立的？注册资本多少？主营产品有哪些板块？（只用知识库内容作答）'
const tail = await rpc('session.history', { sessionId: target, maxMessages: 1 })
let baseline = -1
for (const e of tail.events ?? []) baseline = Math.max(baseline, e.event.seq)
await rpc('session.prompt', { sessionId: target, mode: 'queue', content: [{ type: 'text', text: q }] })
console.log('问题已提交，等待模型…')

for (let i = 0; i < 40; i++) {
  await sleep(5_000)
  const page = await rpc('session.history', { sessionId: target, maxMessages: 20 })
  const fresh = (page.events ?? []).filter(e => e.event.seq > baseline)
  if (fresh.find(e => e.event.type === 'turn/end')) {
    let text = ''
    for (const { event } of fresh) {
      if (event.type !== 'assistant/message') continue
      const c = event.data?.message?.content
      if (Array.isArray(c)) { const t = c.filter(b => b?.type === 'text').map(b => b.text).join(''); if (t) text = t }
    }
    const tools = fresh.filter(e => e.event.type === 'tool/call').map(e => e.event.data?.name)
    console.log('使用工具:', tools.join(', ') || '（无）')
    console.log('--- 回答 ---')
    console.log(text.slice(0, 500))
    process.exit(0)
  }
}
console.log('超时未完成')
