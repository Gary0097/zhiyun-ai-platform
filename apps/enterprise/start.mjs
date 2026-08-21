#!/usr/bin/env node
// 平台启动器：先加载 config/secrets.local.env（不入库的本地密钥）再启动服务
// 用法：node start.mjs [端口]
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const secrets = join(HERE, 'config', 'secrets.local.env')
if (existsSync(secrets)) {
  for (const line of readFileSync(secrets, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$/)
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim()
  }
}
process.argv.splice(1, 1, 'server/index.js') // 让 server/index.js 看到原始参数位
await import('./server/index.js')
