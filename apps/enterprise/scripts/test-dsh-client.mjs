// 复现企业平台 auto-run 的 dsh 调用路径：Node fetch + 信封协议
// 用法：node scripts/test-dsh-client.mjs
const BASE = 'http://127.0.0.1:8308'

async function rpc (method, payload, timeoutMs = 30000) {
  const res = await fetch(`${BASE}/api/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method, payload }),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const body = await res.json()
  const result = body?.result
  if (!result?.ok) throw new Error(`${method}: ${result?.error?.code ?? ''} ${result?.error?.message ?? 'no result'}`)
  return result.value
}

const t0 = Date.now()
const log = (msg) => console.log(`[${Date.now() - t0}ms] ${msg}`)

// 1. session.list 连通性
const list = await rpc('session.list', {})
log(`session.list OK: ${list.items.length} 个会话`)

// 2. 找 jhl 工作区
const ws = await rpc('workspace.list', {})
log(`workspace.list OK: ${ws.items?.length ?? 0} 个工作区`)
const jhl = (ws.items ?? []).find(w => w.path?.includes('jhl'))
if (!jhl) throw new Error('jhl 工作区不存在')
log(`jhl 工作区: ${jhl.workspaceId} (${jhl.title})`)

// 3. 新建会话（预分配 id）
const sessionId = `session-${crypto.randomUUID()}`
const created = await rpc('session.create', { sessionId, workspaceId: jhl.workspaceId })
log(`session.create OK: ${created.sessionId}`)

// 4. 发送 prompt（模拟 auto-run 的问题格式）
const question = '请阅读工作区中的 FUNCTIONS.md 再作答，直接给出结论与建议，不要向用户提问。请用一句话概括本企业的功能清单。'
const promptRes = await rpc('session.prompt', { sessionId, mode: 'queue', content: [{ type: 'text', text: question }] })
log(`session.prompt OK: ${JSON.stringify(promptRes)}`)

// 5. 轮询 history 直到 turn/end（最多 90s）
const deadline = Date.now() + 90_000
let turnEnd = null
while (Date.now() < deadline && !turnEnd) {
  await new Promise(r => setTimeout(r, 3000))
  const page = await rpc('session.history', { sessionId, maxMessages: 20 })
  const types = (page.events ?? []).map(e => e.event.type)
  turnEnd = (page.events ?? []).find(e => e.event.type === 'turn/end')
  log(`history: ${types.length} 事件，类型: ${[...new Set(types)].join(',')}${turnEnd ? ' ← turn/end!' : ''}`)
}

if (turnEnd) {
  log(`turn 结束: reason=${turnEnd.event.data?.reason?.kind}`)
  const page = await rpc('session.history', { sessionId, maxMessages: 20 })
  let text = ''
  for (const { event } of page.events ?? []) {
    if (event.type !== 'assistant/message') continue
    const content = event.data?.message?.content
    if (!Array.isArray(content)) continue
    const t = content.filter(b => b?.type === 'text').map(b => b.text).join('').trim()
    if (t) text = t
  }
  console.log('--- 最终回复 ---')
  console.log(text.slice(0, 300))
} else {
  log('90s 内未等到 turn/end（复现了平台问题！）')
  const page = await rpc('session.history', { sessionId, maxMessages: 20 })
  log(`当前事件: ${(page.events ?? []).map(e => `${e.event.seq}:${e.event.type}`).join(' ')}`)
}
process.exit(0)
