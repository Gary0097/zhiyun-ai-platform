// 确保 Workspace 目录结构就绪（智造云 AIOS 2.2.0 极简形态）
// 2.2.0 登录由 QwenPaw 原生认证承载（QWENPAW_AUTH_ENABLED），不再需要
// zhiyun-auth 的 users.json/token_secret；仅保留运行必需的基础目录。
import { mkdirSync, existsSync, renameSync, readdirSync, copyFileSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const scriptsRoot = dirname(fileURLToPath(import.meta.url))
const appRoot = join(scriptsRoot, '..')
const workspace = join(appRoot, 'workspace')

// Node 24.11.1 on Windows can terminate natively in fs.cpSync when the
// installation path contains Chinese characters. Copy the small brand tree
// using individual filesystem operations; never follow source symlinks.
function copyBrandTree(source, target) {
  mkdirSync(target, { recursive: true })
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const from = join(source, entry.name), to = join(target, entry.name)
    if (entry.isSymbolicLink()) throw new Error('Brand source must not contain symlinks: ' + from)
    if (entry.isDirectory()) copyBrandTree(from, to)
    else if (entry.isFile()) copyFileSync(from, to)
  }
}

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
    copyBrandTree(brandSrc, brandDst)
    console.log(`  [brand] aios-brand v${manifest.version} 已同步到 workspace/plugins`)
  }
}

console.log('Workspace 目录结构已就绪。')

// 办公专属默认技能包预置（aios-office 分支）：把仓库 skills/office 同步到
// 技能池与全部智能体工作区并默认启用。动态导入 + 存在性检查：技能包或脚本
// 缺失（如测试单文件拷贝、裁剪安装）时静默跳过；预置失败不阻断启动。
const officeProvisioner = join(scriptsRoot, 'provision-office-skills.mjs')
const officePackRoot = join(appRoot, '..', '..', 'skills', 'office')
if (existsSync(officeProvisioner) && existsSync(join(officePackRoot, 'office-pack.json'))) {
  try {
    const { provisionOfficeSkills } = await import(pathToFileURL(officeProvisioner).href)
    provisionOfficeSkills({ workspace, packRoot: officePackRoot })
  } catch (e) {
    console.warn('办公技能包预置失败（不影响启动，可重跑 start-ai-os 重试）：', e.message)
  }
}

// 办公技能包依赖预装（docx/excel/ppt/pdf/OCR 等常用包）：启动期幂等安装到
// 项目 venv，避免技能执行期临时 pip install。同样缺文件静默跳过、失败不阻断。
const officeDeps = join(scriptsRoot, 'ensure-office-deps.mjs')
if (existsSync(officeDeps) && existsSync(join(officePackRoot, 'requirements-office.txt'))) {
  try {
    const { ensureOfficeDependencies } = await import(pathToFileURL(officeDeps).href)
    ensureOfficeDependencies({ appRoot, packRoot: officePackRoot })
  } catch (e) {
    console.warn('办公依赖预装失败（不影响启动）：', e.message)
  }
}

// ZCode 默认办公技能桥接（完全体）：本机装有 ZCode 时，把其官方办公插件
// 技能注册为外部技能根（原地引用不复制，未安装则静默跳过）。
const zcodeBridge = join(scriptsRoot, 'link-zcode-skills.mjs')
if (existsSync(zcodeBridge)) {
  try {
    const { linkZcodeSkills } = await import(pathToFileURL(zcodeBridge).href)
    linkZcodeSkills({ workspace })
  } catch (e) {
    console.warn('ZCode 技能桥接失败（不影响启动）：', e.message)
  }
}
