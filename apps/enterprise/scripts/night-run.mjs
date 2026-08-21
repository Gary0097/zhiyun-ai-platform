// 夜间排程器（Night Scheduler）
// 拉满排程到目标时刻（默认当日 07:00）自动停。轮转任务：
//   知识收割（Qwen27B 加工联网资料入库）→ 功能模块演示（28 项）→ 业务角色（6 角色）
//   → 金汉隆报告 → 企业业务数据再生成 →（每 2 小时一轮知识收割查漏补缺）
// 用法：node scripts/night-run.mjs [HH:mm 截止时刻，默认 07:00]
const BASE = 'http://127.0.0.1:8390'
const DEADLINE_HM = process.argv[2] || '07:00'

const log = msg => console.log(`[night ${new Date().toISOString().replace('T', ' ').slice(11, 19)}] ${msg}`)
const sleep = ms => new Promise(r => setTimeout(r, ms))

function deadline () {
  const [h, m] = DEADLINE_HM.split(':').map(Number)
  const d = new Date()
  d.setHours(h, m, 0, 0)
  if (d <= new Date()) d.setDate(d.getDate() + 1) // 已过则视为明天
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
  const r = await api('POST', '/api/auth/login', { username: 'admin.a', password: 'Zhiyun@2026' })
  return r.token
}

/** 等待自动运行器回到 idle（轮询 status） */
async function waitAutoRunIdle (token, label) {
  for (let i = 0; i < 240; i++) { // 最多 2 小时
    await sleep(30_000)
    try {
      const st = await api('GET', '/api/autorun/status', null, token)
      if (st.state === 'idle') { log(`${label} 完成（本轮 done=${st.done} failed=${st.failed}）`); return true }
      if (i % 8 === 0) log(`${label} 进行中…（${st.done + st.failed}/${st.total}）`)
    } catch (e) { log(`status 查询失败: ${e.message}（继续等待）`) }
  }
  log(`${label} 超过 2 小时未结束，跳到下一任务`)
  return false
}

/** 等待知识收割完成 */
async function waitHarvest (token) {
  for (let i = 0; i < 60; i++) { // 最多 30 分钟
    await sleep(30_000)
    try {
      const st = await api('GET', '/api/knowledge/harvest-status', null, token)
      if (!st.running) { log(`知识收割完成（新增 ${st.items} 条${st.error ? '，错误: ' + st.error : ''}）`); return }
    } catch { /* 重试 */ }
  }
  log('知识收割等待超时，继续')
}

async function main () {
  const end = deadline()
  log(`夜间排程启动，截止 ${DEADLINE_HM}（剩余 ${((end - Date.now()) / 3600000).toFixed(1)} 小时）`)
  let token = await login()
  let relogin = Date.now() + 2 * 3600_000 // token 2 小时刷新一次
  let harvestCount = 0
  let round = 0
  let lastHarvest = 0
  let consecutiveFailures = 0

  const tasks = [
    { name: '知识收割（联网资料加工）', run: async () => { await api('POST', '/api/knowledge/harvest', {}, token); await waitHarvest(token); harvestCount++; lastHarvest = Date.now() } },
    { name: '功能模块演示（28 项）', run: async () => { await api('POST', '/api/autorun/start', { rounds: 1, concurrency: 2, scope: 'features' }, token); await waitAutoRunIdle(token, '功能模块演示') } },
    { name: '业务角色运行（6 角色）', run: async () => { await api('POST', '/api/autorun/start', { rounds: 1, concurrency: 2, scope: 'business' }, token); await waitAutoRunIdle(token, '业务角色运行') } },
    { name: '金汉隆数据报告', run: async () => { await api('POST', '/api/autorun/report/rerun', {}, token); await sleep(180_000) /* 报告约 1-3 分钟，不精确等待 */ } },
    { name: '多 Agent 协同测试', run: async () => { await api('POST', '/api/autorun/multiagent', {}, token); await sleep(300_000) /* 三段乒乓约 4-5 分钟 */ } },
    { name: '企业业务数据再生成', run: async () => { const r = await api('POST', '/api/business/generate', { months: 6, clear: true }, token); log(`业务数据再生成: ${r.orders} 订单`) } },
  ]

  while (Date.now() < end.getTime()) {
    round++
    // token 刷新
    if (Date.now() > relogin) { try { token = await login(); relogin = Date.now() + 2 * 3600_000; log('token 已刷新') } catch (e) { log('token 刷新失败: ' + e.message) } }
    // 服务掉线保护：连续失败达到阈值说明平台挂了，退避等待恢复（最多等到截止时刻）
    if (consecutiveFailures >= 3) {
      const backoff = Math.min(5 * 60_000, end.getTime() - Date.now())
      if (backoff > 0) { log(`平台连续 ${consecutiveFailures} 次失败，退避 ${Math.round(backoff / 1000)}s 等待恢复…`); await sleep(backoff) }
      try { token = await login(); consecutiveFailures = 0; log('平台已恢复，重新登录') } catch { /* 仍不可用，下轮继续退避 */ }
    }
    log(`── 第 ${round} 轮开始（剩余 ${((end.getTime() - Date.now()) / 3600000).toFixed(1)}h）──`)
    let roundFailed = true
    for (const task of tasks) {
      if (Date.now() >= end.getTime()) break
      // 知识收割：首轮必跑，之后每 2 小时补一轮（查漏补缺，幂等跳过已有条目）
      if (task.name.startsWith('知识收割') && harvestCount > 0 && Date.now() - lastHarvest < 2 * 3600_000) continue
      try {
        log(`任务: ${task.name}`)
        await task.run()
        roundFailed = false
      } catch (e) {
        log(`任务失败 ${task.name}: ${e.message}`)
        if (e.status === 401) { try { token = await login(); log('重新登录成功') } catch { /* 下一轮再试 */ } }
        if (String(e.message).includes('fetch')) { consecutiveFailures++; break } // 平台不可达，跳出本轮任务序列
      }
    }
    if (!roundFailed) consecutiveFailures = 0
    // 轮间歇（拉满模式：仅 60s 缓冲）
    if (Date.now() < end.getTime()) { log('轮间歇 60s'); await sleep(60_000) }
  }
  log(`到达截止时刻 ${DEADLINE_HM}，夜间排程结束（共 ${round} 轮，知识收割 ${harvestCount} 次）`)
}

main().catch(e => { log('排程器异常退出: ' + e.message); process.exit(1) })
