// 确保 Workspace 目录结构就绪（智造云 AIOS 2.2.0 极简形态）
// 2.2.0 登录由 QwenPaw 原生认证承载（QWENPAW_AUTH_ENABLED），不再需要
// zhiyun-auth 的 users.json/token_secret；仅保留运行必需的基础目录。
import { mkdirSync, existsSync, renameSync, readdirSync } from 'node:fs'
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

// 1.x → 2.2.0 升级迁移：仅当 plugins 目录中存在已知的 1.x 业务插件
// （zhiyun-* / qwenpaw-creator* / agent-kanban）时才整体移出——2.2.0 之后
// 用户自行安装的兼容插件不受影响。只做可恢复的移出，绝不删除用户内容；
// 移出后目录不存在，逻辑天然幂等。
const legacyPrefixes = ['zhiyun-', 'qwenpaw-creator', 'agent-kanban']
const legacyPlugins = join(workspace, 'plugins')
if (existsSync(legacyPlugins)) {
  let entries = []
  try { entries = readdirSync(legacyPlugins) } catch { }
  const hasLegacy = entries.some(name => legacyPrefixes.some(p => name.startsWith(p)))
  if (hasLegacy) {
    const backup = join(workspace, 'plugins.legacy-backup-' + new Date().toISOString().replace(/[:.]/g, '-'))
    renameSync(legacyPlugins, backup)
    console.log('  [migrate] 1.x 业务插件目录已移至可恢复备份')
  }
}

console.log('Workspace 目录结构已就绪。')
