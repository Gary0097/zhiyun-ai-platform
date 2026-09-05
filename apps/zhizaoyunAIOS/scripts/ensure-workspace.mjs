// 确保 Workspace 目录结构就绪（智造云 AIOS 2.2.0 极简形态）
// 2.2.0 登录由 QwenPaw 原生认证承载（QWENPAW_AUTH_ENABLED），不再需要
// zhiyun-auth 的 users.json/token_secret；仅保留运行必需的基础目录。
import { mkdirSync, existsSync, renameSync, readdirSync, cpSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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

// 1.x → 2.2.0 升级迁移：只移出已知 1.x 业务插件子目录（zhiyun-* /
// qwenpaw-creator* / agent-kanban），混合目录中用户自装的兼容插件原地保留。
// 只做可恢复的移出，绝不删除用户内容；目录为空后移除空壳。
// 1.x 已退役业务插件的精确目录名（后续回归的独立插件用新 ID，不受影响）
const legacyPluginIds = [
  'zhiyun-auth', 'zhiyun-audit', 'zhiyun-logo', 'zhiyun-data-core', 'zhiyun-data-insights',
  'zhiyun-enterprise-seeder', 'zhiyun-app-discovery',
  'qwenpaw-creator-studio', 'qwenpaw-creator', 'qwenpaw-creator-mixcut', 'agent-kanban',
]
const legacyPlugins = join(workspace, 'plugins')
if (existsSync(legacyPlugins)) {
  let entries = []
  try { entries = readdirSync(legacyPlugins) } catch { }
  const legacyDirs = entries.filter(name => legacyPluginIds.includes(name))
  if (legacyDirs.length) {
    const backup = join(workspace, 'plugins.legacy-backup-' + new Date().toISOString().replace(/[:.]/g, '-'))
    mkdirSync(backup, { recursive: true })
    for (const name of legacyDirs) {
      renameSync(join(legacyPlugins, name), join(backup, name))
      console.log('  [migrate] 1.x 业务插件已移至可恢复备份：' + name)
    }
    let rest = []
    try { rest = readdirSync(legacyPlugins) } catch { }
    if (!rest.length) {
      try { renameSync(legacyPlugins, legacyPlugins + '.empty-removed') } catch { }
    }
  }
}

// 品牌层插件同步：把仓库 plugins/aios-brand 复制到 workspace/plugins（版本
// 变化才覆盖，幂等）。这是 #126 的官方扩展点形态——QwenPaw 升级不需重建。
const brandSrc = join(appRoot, '..', '..', 'plugins', 'aios-brand')
const brandDst = join(workspace, 'plugins', 'aios-brand')
if (existsSync(join(brandSrc, 'plugin.json'))) {
  let need = true
  const manifest = JSON.parse(readFileSync(join(brandSrc, 'plugin.json'), 'utf8'))
  try {
    const installed = JSON.parse(readFileSync(join(brandDst, 'plugin.json'), 'utf8'))
    need = installed.version !== manifest.version
  } catch { }
  if (need) {
    mkdirSync(join(workspace, 'plugins'), { recursive: true })
    rmSync(brandDst, { recursive: true, force: true })
    cpSync(brandSrc, brandDst, { recursive: true })
    console.log(`  [brand] aios-brand v${manifest.version} 已同步到 workspace/plugins`)
  }
}

console.log('Workspace 目录结构已就绪。')
