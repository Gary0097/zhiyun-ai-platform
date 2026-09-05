// 确保 Workspace 目录结构就绪（智造云 AIOS 2.2.0 极简形态）
// 2.2.0 登录由 QwenPaw 原生认证承载（QWENPAW_AUTH_ENABLED），不再需要
// zhiyun-auth 的 users.json/token_secret；仅保留运行必需的基础目录。
import { mkdirSync, existsSync, renameSync } from 'node:fs'
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

// 1.x → 2.2.0 升级迁移：旧安装的 workspace/plugins 里有历史业务插件
// （zhiyun-auth / zhiyun-audit / creator 等），2.2.0 极简形态不再加载它们。
// 只做可恢复的移出（plugins.legacy-backup-<ts>），绝不删除用户内容；
// 目录已被移走后本逻辑自然幂等。
const legacyPlugins = join(workspace, 'plugins')
if (existsSync(legacyPlugins)) {
  const backup = join(workspace, 'plugins.legacy-backup-' + new Date().toISOString().replace(/[:.]/g, '-'))
  renameSync(legacyPlugins, backup)
  console.log('  [migrate] 1.x 插件目录已移至可恢复备份：' + backup.split(/[\/]/).pop())
}

console.log('Workspace 目录结构已就绪。')
