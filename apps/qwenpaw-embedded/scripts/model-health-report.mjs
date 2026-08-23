const baseUrl = process.env.AI_OS_URL || 'http://127.0.0.1:8088'
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

async function fetchJson (path, options) {
  const response = await fetch(`${baseUrl}${path}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`)
  return body
}

async function main () {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const active = await fetchJson('/api/models/active?scope=effective&agent_id=default')
      const model = active.active_llm
      if (!model || !model.provider_id || !model.model) {
        console.warn('⚠️ 模型诊断：默认智能体尚未选择模型。请进入“模型”选择并测试一个可用模型。')
        return
      }
      const tested = await fetchJson(`/api/models/${encodeURIComponent(model.provider_id)}/models/test`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_id: model.model })
      })
      if (tested.success) console.log(`✅ 模型诊断：${model.provider_id}/${model.model} 连接正常`)
      else console.warn(`⚠️ 模型诊断：${model.provider_id}/${model.model} 无法连接。${tested.message || '请在“模型”页面执行连接测试并检查网络、代理或密钥。'}`)
      return
    } catch (error) {
      if (attempt < 29) { await wait(1000); continue }
      console.warn(`⚠️ 模型诊断暂不可用：${error.message}。应用仍可使用；智能体对话前请在“模型”页面执行连接测试。`)
    }
  }
}

await main()
