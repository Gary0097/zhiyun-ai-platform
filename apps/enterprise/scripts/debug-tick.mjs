// 直接对本地服务调用 tick 并打印完整响应
const PORT = 8095
const BASE = `http://127.0.0.1:${PORT}`
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
const HERE = dirname(fileURLToPath(import.meta.url))
const server = spawn(process.execPath, [join(HERE, '..', 'server', 'index.js')], { env: { ...process.env, PORT: String(PORT) }, stdio: ['ignore', 'inherit', 'inherit'] })
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
for (let i = 0; i < 40; i++) { try { await fetch(BASE + '/'); break } catch { await sleep(500) } }
const login = await (await fetch(BASE + '/api/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ username: 'admin.a', password: 'Zhiyun@2026' }) })).json()
console.log('--- 调用 /api/scheduler/tick ---')
const t0 = Date.now()
const res = await fetch(BASE + '/api/scheduler/tick', { method: 'POST', headers: { authorization: 'Bearer ' + login.token } })
console.log('状态:', res.status, '耗时:', Date.now() - t0, 'ms')
console.log('响应:', JSON.stringify(await res.json()))
server.kill()
process.exit(0)
