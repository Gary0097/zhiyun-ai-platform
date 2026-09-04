// 确保 Workspace 目录结构就绪（智造云 AIOS 2.2.0 极简形态）
// 2.2.0 登录由 QwenPaw 原生认证承载（QWENPAW_AUTH_ENABLED），不再需要
// zhiyun-auth 的 users.json/token_secret；仅保留运行必需的基础目录。
import { mkdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const appRoot = join(scriptsRoot, '..')
const workspace = join(appRoot, 'workspace')

const dirs = [
  'workspaces/default/logs',
  'workspaces/default/sessions/console',
  'workspaces/default/data',
  'workspaces/default/files',
  'workspaces/default/knowledge',
]

for (const dir of dirs) {
  const full = join(workspace, dir)
  if (!existsSync(full)) {
    mkdirSync(full, { recursive: true })
    console.log(`  [init] ${dir}/`)
  }
}

console.log('Workspace 目录结构已就绪。')
