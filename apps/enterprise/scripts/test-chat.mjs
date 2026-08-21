// 端到端对话测试（文件方式确保 UTF-8，避免 shell 编码问题）
const BASE = 'http://127.0.0.1:8390'
const api = async (method, path, body, token) => {
  const res = await fetch(BASE + path, { method, headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) }, body: body ? JSON.stringify(body) : undefined })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { status: res.status })
  return data
}
const main = async () => {
  const login = await api('POST', '/api/auth/login', { username: 'admin.a', password: 'Zhiyun@2026' })
  const T = login.token
  const agents = await api('GET', '/api/chat/agents', null, T)
  const assistant = agents.find(a => a.agent_name === '企业智能助手')
  // 无会话直接发消息（模拟用户不点新对话直接输入）
  const conv = await api('POST', '/api/conversations', { agent_id: assistant.agent_id }, T)
  const r = await api('POST', `/api/conversations/${conv.id}/chat`, { content: '你好，我们现在有多少在产订单？' }, T)
  console.log('✅ 正常中文对话:', r.status, '|', (r.reply || '').slice(0, 120).replace(/\n/g, ' '))
  // 乱码拦截
  try {
    await api('POST', `/api/conversations/${conv.id}/chat`, { content: '你好��订单' }, T)
    console.log('❌ 乱码未被拦截')
  } catch (e) {
    console.log('✅ 乱码拦截:', e.status, e.message)
  }
  // 多轮上下文
  const r2 = await api('POST', `/api/conversations/${conv.id}/chat`, { content: '其中风险最高的是哪个？' }, T)
  console.log('✅ 多轮上下文:', (r2.reply || '').slice(0, 100).replace(/\n/g, ' '))
  process.exit(0)
}
main().catch(e => { console.error('失败:', e.message); process.exit(1) })
