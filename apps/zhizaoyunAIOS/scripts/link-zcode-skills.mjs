// 智造云 AIOS × ZCode 默认办公技能桥接（aios-office 分支"完全体"）
// 本机安装了 ZCode 时，把其官方办公插件技能（pptx/xlsx/docx/pdf/浏览器/
// 电脑操作/搜图等）注册为 QwenPaw 外部技能根（config.json 的 skill_paths）：
//   - 技能原地读取、不复制进仓库——ZCode 技能为专有授权内容，不得再分发；
//   - 未安装 ZCode 的机器路径不存在，QwenPaw 会静默跳过，零副作用；
//   - 外部根排在主技能池之后：同名时主池优先（QwenPaw 官方遮蔽规则），
//     office-* 技能与内置技能均不受影响；
//   - 幂等：仅新增缺失路径，绝不改动用户自配的其他 skill_paths 条目。
import { homedir } from 'node:os'
import { existsSync as fsExists, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

// ZCode 官方插件缓存中与办公相关的插件 id（版本目录取最新）
const OFFICE_PLUGIN_IDS = [
  'presentations',   // pptx
  'spreadsheets',    // xlsx
  'documents',       // docx
  'pdf',             // pdf
  'browser-use',     // 浏览器操控（control-browser / web-gui-tester）
  'computer-use',    // 电脑操作
  'image-search',    // 搜图
]

export function defaultZcodeRoot () {
  return join(homedir(), '.zcode', 'cli', 'plugins', 'cache', 'zcode-plugins-official')
}

// 找出一个插件 id 下最新版本目录里的 skills 目录（无则返回 null）
export function latestSkillsDir (pluginRoot) {
  if (!fsExists(pluginRoot)) return null
  const versions = readdirSync(pluginRoot, { withFileTypes: true })
    .filter(e => e.isDirectory() && /^\d+\.\d+/.test(e.name))
    .map(e => e.name)
  if (!versions.length) return null
  const byVersion = (a, b) => {
    const pa = a.split('.').map(Number), pb = b.split('.').map(Number)
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const d = (pb[i] || 0) - (pa[i] || 0)
      if (d) return d
    }
    return 0
  }
  for (const v of versions.sort(byVersion)) {
    const skills = join(pluginRoot, v, 'skills')
    if (fsExists(join(skills))) {
      const hasSkill = readdirSync(skills, { withFileTypes: true })
        .some(e => e.isDirectory() && fsExists(join(skills, e.name, 'SKILL.md')))
      if (hasSkill) return skills
    }
  }
  return null
}

export function linkZcodeSkills ({ workspace, zcodeRoot, pluginIds = OFFICE_PLUGIN_IDS, log = console.log } = {}) {
  if (!workspace) throw new Error('linkZcodeSkills 需要 workspace 参数')
  const root = zcodeRoot || process.env.ZCODE_SKILLS_ROOT || defaultZcodeRoot()
  if (!fsExists(root)) return { status: 'not-installed', paths: [] }

  const found = []
  for (const id of pluginIds) {
    const skillsDir = latestSkillsDir(join(root, id))
    if (skillsDir) found.push(skillsDir)
  }
  if (!found.length) return { status: 'not-installed', paths: [] }

  // 合并进 config.json 的 skill_paths（保留用户已有条目，去重，原子写）
  const configPath = join(workspace, 'config.json')
  let config = {}
  try { config = JSON.parse(readFileSync(configPath, 'utf8')) } catch { /* 无配置则新建骨架 */ }
  const existing = Array.isArray(config.skill_paths) ? config.skill_paths : []
  const additions = found.filter(p => !existing.includes(p))
  if (!additions.length) return { status: 'up-to-date', paths: existing }

  config.skill_paths = [...existing, ...additions]
  const tmp = configPath + '.tmp-zcode-link'
  writeFileSync(tmp, JSON.stringify(config, null, 2) + '\n', 'utf8')
  renameSync(tmp, configPath)
  for (const p of additions) log('  [zcode-bridge] 外部技能根已注册：' + p)
  log(`  [zcode-bridge] ZCode 办公技能桥接完成：新增 ${additions.length} 个技能根（原地引用，不复制）。`)
  return { status: 'linked', added: additions, paths: config.skill_paths }
}

// ---------- CLI ----------
// 用法：node link-zcode-skills.mjs [--workspace <dir>] [--zcode-root <dir>] [--check]
// --check：只校验桥接模块与根目录解析（发布门禁用），不写任何文件。
const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  const args = process.argv.slice(2)
  const argValue = flag => {
    const i = args.indexOf(flag)
    return i >= 0 && args[i + 1] ? args[i + 1] : null
  }
  const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
  const workspace = argValue('--workspace') || process.env.QWENPAW_WORKING_DIR || join(appRoot, 'workspace')

  if (args.includes('--check')) {
    const root = argValue('--zcode-root') || process.env.ZCODE_SKILLS_ROOT || defaultZcodeRoot()
    console.log(`ZCode 技能桥接校验通过：插件清单 ${OFFICE_PLUGIN_IDS.length} 项，根目录 ${fsExists(root) ? '已安装（' + root + '）' : '未安装（本机跳过，其他机器按需生效）'}。`)
  } else {
    linkZcodeSkills({ workspace, zcodeRoot: argValue('--zcode-root') || undefined })
  }
}
