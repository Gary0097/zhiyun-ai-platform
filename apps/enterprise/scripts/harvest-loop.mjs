// 知识收割自动循环（Knowledge Harvest Loop）
// 持续自动搜集→加工→灌入知识库，到截止时刻自动停。
// 每轮 = 一次完整收割（一个研究包的 4-5 个主题，约 5-15 分钟）+ 间隔缓冲。
// 幂等去重保证重复轮次不会产生重复条目（同标题跳过）。
// 用法：node scripts/harvest-loop.mjs [HH:mm 截止时刻，默认 14:00]
const BASE = 'http://127.0.0.1:8390'

const log = msg => console.log(`[harvest-loop ${new Date().toISOString().replace('T', ' ').slice(11, 19)}] ${msg}`)
const sleep = ms => new Promise(r => setTimeout(r, ms))

function deadline () {
  const [h, m] = (process.argv[2] || '14:00').split(':').map(Number)
  const d = new Date()
  d.setHours(h, m, 0, 0)
  if (d <= new Date()) d.setDate(d.getDate() + 1)
  return d
}

async function api (method, path, body, token) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(120_000),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { status: res.status })
  return data
}

async function login () {
  return (await api('POST', '/api/auth/login', { username: 'admin.a', password: 'Zhiyun@2026' })).token
}

async function waitHarvest (token) {
  for (let i = 0; i < 60; i++) { // 最多 30 分钟
    await sleep(30_000)
    try {
      const st = await api('GET', '/api/knowledge/harvest-status', null, token)
      if (!st.running) return st
    } catch { /* 重试 */ }
  }
  return null
}

async function main () {
  const end = deadline()
  log(`知识收割自动循环启动，截止 ${(process.argv[2] || '14:00')}（剩余 ${((end - Date.now()) / 3600000).toFixed(1)} 小时）`)
  let token = await login()
  let round = 0
  let totalAdded = 0
  let consecutiveFailures = 0

  while (Date.now() < end.getTime()) {
    round++
    // 服务掉线保护（复用 night-run 验证过的退避模式）
    if (consecutiveFailures >= 3) {
      log(`平台连续 ${consecutiveFailures} 次失败，退避 2 分钟等待恢复…`)
      await sleep(120_000)
      try { token = await login(); consecutiveFailures = 0; log('平台已恢复') } catch { continue }
    }
    try {
      log(`── 第 ${round} 轮收割（剩余 ${((end.getTime() - Date.now()) / 3600000).toFixed(1)}h）──`)
      await api('POST', '/api/knowledge/harvest', {}, token)
      const st = await waitHarvest(token)
      if (st) {
        totalAdded += st.items || 0
        log(`本轮完成：新增 ${st.items} 条（研究包「${st.lastPack || '?'}」）${st.error ? '错误: ' + st.error : ''}，累计 ${totalAdded} 条`)
        if (!st.error) consecutiveFailures = 0
      } else {
        log('本轮等待超时（30 分钟），继续下一轮')
      }
    } catch (e) {
      consecutiveFailures++
      log(`收割失败: ${e.message}`)
      if (e.status === 401) { try { token = await login() } catch { /* 下轮退避 */ } }
    }
    // 轮间歇 2 分钟（让模型网关喘息；幂等去重下多轮安全）
    if (Date.now() < end.getTime()) { log('间歇 120s'); await sleep(120_000) }
  }
  log(`到达截止时刻，知识收割循环结束（共 ${round} 轮，累计新增 ${totalAdded} 条知识）`)
}

main().catch(e => { log('循环异常退出: ' + e.message); process.exit(1) })
