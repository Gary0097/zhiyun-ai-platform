// 智造云企业 AI 智能体平台 · 服务入口
import { createServer } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, extname } from 'node:path'
import { init, db, DATA_DIR } from './db.js'
import { buildRoutes } from './routes.js'
import { authenticate } from './auth.js'
import { startSchedulerLoop } from './scheduler.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const PORT = Number(process.env.PORT || 8390)

init()

const routes = buildRoutes()
const routeMap = new Map()
for (const r of routes) {
  const keys = []
  const regex = new RegExp('^' + r.path.replace(/:([A-Za-z]+)/g, (_, k) => { keys.push(k); return '([^/]+)' }) + '$')
  routeMap.set(`${r.method} ${r.path}`, { ...r, keys, regex })
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' }

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost')
    const path = url.pathname

    if (!path.startsWith('/api/')) {
      // 品牌 Logo（存于 data/ 目录，按 business_setting 当前值提供）
      if (path === '/logo.png') {
        const logoFile = db.prepare('SELECT value FROM business_setting WHERE key = ?').get('brand.logo')?.value
        const full = logoFile ? join(DATA_DIR, logoFile) : null
        if (logoFile && existsSync(full)) {
          res.writeHead(200, { 'content-type': MIME[extname(full)] || 'image/png', 'cache-control': 'no-store' })
          res.end(readFileSync(full))
          return
        }
        res.writeHead(404).end()
        return
      }
      const file = path === '/' ? '/index.html' : path
      const full = join(HERE, '..', 'public', file)
      if (existsSync(full) && full.startsWith(join(HERE, '..', 'public'))) {
        res.writeHead(200, { 'content-type': MIME[extname(full)] || 'application/octet-stream', 'cache-control': extname(full) === '.html' ? 'no-store' : 'max-age=3600' })
        res.end(readFileSync(full))
        return
      }
      res.writeHead(404).end('Not Found')
      return
    }

    // 路由匹配（含 :params）
    let matched = null; let params = {}
    for (const r of routeMap.values()) {
      if (r.method !== req.method) continue
      const m = path.match(r.regex)
      if (m) { matched = r; params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])); break }
    }
    if (!matched) { res.writeHead(404, { 'content-type': 'application/json' }).end(JSON.stringify({ error: '接口不存在' })); return }

    const needsAuth = path !== '/api/auth/login'
    const user = needsAuth ? authenticate(req) : null
    const data = await matched.handler(req, res, { user, params })
    if (!res.writableEnded) res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' }).end(JSON.stringify(data ?? { ok: true }))
  } catch (e) {
    const status = e.status || 500
    if (!res.writableEnded) res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' }).end(JSON.stringify({ error: e.message, pendingConfirm: e.pendingConfirm || undefined }))
  }
})

server.listen(PORT, () => {
  console.log(`智造云企业 AI 智能体平台已启动: http://127.0.0.1:${PORT}`)
  console.log('默认账号: admin.a / platform / admin.b / admin.c，密码统一 Zhiyun@2026')
})
startSchedulerLoop(30000)
