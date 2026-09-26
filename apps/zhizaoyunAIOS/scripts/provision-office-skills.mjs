// 智造云 AIOS 办公专属默认技能包预置（aios-office 分支）
// 参考 ZCode 办公模式：把仓库 skills/office 下的办公技能包预置进
// QwenPaw 工作区（$QWENPAW_WORKING_DIR）——
//   1) 技能池 skill_pool/<name>/（全部工作区可复用，清单 skill.json）；
//   2) 每个智能体工作区 workspaces/<agent_id>/skills/<name>/ 并在
//      工作区 skill.json 中登记为默认启用（enabled: true）。
// 幂等：以内容哈希记录同步状态，未变化不重写；用户在池/工作区中自行修改过
// 的技能不覆盖（告警跳过）；用户自建的同名技能绝不触碰。
// 清单格式与 QwenPaw 2.2.1 技能系统一致（workspace-skill-manifest.v1 /
// skill-pool-manifest.v1），调和逻辑会保留 enabled/channels/installed_from。
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const STATE_FILE = '.office-pack.json'
const WORKSPACE_MANIFEST_SCHEMA = 'workspace-skill-manifest.v1'
const POOL_MANIFEST_SCHEMA = 'skill-pool-manifest.v1'
const INSTALLED_FROM = 'office-pack'

// ---------- 办公回复规范（v1.3.0：每轮系统提示词瘦身 + 输出纪律） ----------
// QwenPaw 默认每轮注入 AGENTS.md+SOUL.md+PROFILE.md（约 4300 字符）。办公版用
// 精简 OFFICE.md（含安全三行与回复/交付纪律）替换泛用的 AGENTS.md，保留
// SOUL.md（人格）与 PROFILE.md（用户资料）：每轮省约 1900 字符，且"先结论、
// 不复述、控制长度"直接压缩输出 token。仅当注入列表为默认三件套时替换，
// 用户自定义过一律不动；OFFICE.md 被用户改过后同样保留现场。
const OFFICE_PROMPT_FILE = 'OFFICE.md'
const DEFAULT_PROMPT_FILES = ['AGENTS.md', 'SOUL.md', 'PROFILE.md']
const OFFICE_PROMPT_TARGET = ['OFFICE.md', 'SOUL.md', 'PROFILE.md']
const OFFICE_PROMPT = [
  '# 智造云 AIOS 办公助手',
  '',
  '- 安全：绝不泄露私密数据与凭据；破坏性命令、发送类操作先确认；删除优先可恢复方式。',
  '- 回复精炼：先给结论或交付物，再给必要说明；不复述问题，不写客套话；并列信息用表格/列表；单条回复默认不超过 300 字，深度细节写进文件交付。',
  '- 文件产出：保存到工作区文件目录，命名「主题_v1.扩展名」；改稿递增版本，绝不覆盖用户原件；交付时说明文件名与位置。',
  '- 事实纪律：数据与结论须来自用户材料或检索结果并注明来源；查不到就明说，不编造。',
  '- 能力路由：办公任务优先调用 office-* 技能（PPT/Excel/Word/PDF/OCR/文件读取/电脑操作/浏览器/搜图/查资料/内容编排）；需要深度工作流时可用技能池中的 ZCode 技能（pptx/xlsx/docx/pdf 等）。',
  '',
].join('\n')

function ensureOfficePrompt (targetDir, targetState, log) {
  const changed = { file: false, config: false }
  const officeMd = join(targetDir, OFFICE_PROMPT_FILE)
  const promptHash = createHash('sha256').update(OFFICE_PROMPT).digest('hex')
  if (!existsSync(officeMd)) {
    writeFileSync(officeMd, OFFICE_PROMPT, 'utf8')
    targetState[OFFICE_PROMPT_FILE] = promptHash
    changed.file = true
  } else {
    const current = readFileSync(officeMd, 'utf8')
    if (current === OFFICE_PROMPT) {
      targetState[OFFICE_PROMPT_FILE] = promptHash
    } else if (targetState[OFFICE_PROMPT_FILE] && targetState[OFFICE_PROMPT_FILE] === createHash('sha256').update(current).digest('hex')) {
      // 我们预置且用户未改动 → 允许随包升级
      writeFileSync(officeMd, OFFICE_PROMPT, 'utf8')
      targetState[OFFICE_PROMPT_FILE] = promptHash
      changed.file = true
    } else {
      log(`  [office] ${OFFICE_PROMPT_FILE} 已被用户修改，保留现场`)
    }
  }
  const agentJsonPath = join(targetDir, 'agent.json')
  if (existsSync(agentJsonPath)) {
    const agent = safeJson(agentJsonPath, null)
    if (agent && typeof agent === 'object') {
      const spf = agent.system_prompt_files
      const isDefaultList = spf === undefined || JSON.stringify(spf) === JSON.stringify(DEFAULT_PROMPT_FILES)
      if (isDefaultList) {
        agent.system_prompt_files = [...OFFICE_PROMPT_TARGET]
        writeJsonAtomic(agentJsonPath, agent)
        changed.config = true
      } else if (JSON.stringify(spf) !== JSON.stringify(OFFICE_PROMPT_TARGET)) {
        log('  [office] system_prompt_files 已被用户自定义，不修改注入列表')
      }
    }
  }
  return changed
}

// ---------- 基础文件操作（不用 fs.cpSync：见 ensure-workspace.mjs 的
// 中文路径原生崩溃记录；同因禁止符号链接） ----------
function copyTree (source, target) {
  mkdirSync(target, { recursive: true })
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const from = join(source, entry.name)
    const to = join(target, entry.name)
    if (entry.isSymbolicLink()) throw new Error('办公技能包源目录不得包含符号链接：' + from)
    if (entry.isDirectory()) copyTree(from, to)
    else if (entry.isFile()) {
      mkdirSync(dirname(to), { recursive: true })
      writeFileSync(to, readFileSync(from))
    }
  }
}

function hashTree (root) {
  const hash = createHash('sha256')
  const walk = dir => {
    const entries = readdirSync(dir, { withFileTypes: true }).filter(e => e.isFile() || e.isDirectory())
    entries.sort((a, b) => a.name.localeCompare(b.name))
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) { hash.update('d:' + entry.name + '\n'); walk(full) }
      else if (entry.isFile()) {
        hash.update('f:' + entry.name + '\n')
        hash.update(readFileSync(full))
      }
    }
  }
  if (existsSync(root)) walk(root)
  else hash.update('<missing>')
  return hash.digest('hex')
}

function writeJsonAtomic (path, data) {
  const tmp = path + '.tmp-office-pack'
  writeFileSync(tmp, JSON.stringify(data, null, 2) + '\n', 'utf8')
  renameSync(tmp, path)
}

// ---------- SKILL.md frontmatter 解析（受控解析：技能包由本仓库 authored，
// 仅支持单行标量 + 两级缩进的 metadata/metadata.qwenpaw 小节） ----------
export function parseSkillFrontmatter (text) {
  const lines = text.split(/\r?\n/)
  if (lines[0] !== '---') throw new Error('SKILL.md 缺少 frontmatter 起始分隔符')
  const end = lines.indexOf('---', 1)
  if (end < 0) throw new Error('SKILL.md frontmatter 未闭合')
  const out = { name: '', description: '', version: '', emoji: '' }
  let section = null, subSection = null
  for (const line of lines.slice(1, end)) {
    if (!line.trim() || line.trim().startsWith('#')) continue
    const top = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/)
    if (top && !line.startsWith(' ')) { section = top[1]; subSection = null; if (top[2]) assign(section, top[2]); continue }
    const nested = line.match(/^ {2}([A-Za-z_][\w-]*):\s*(.*)$/)
    if (nested && section) { subSection = nested[1]; if (nested[2]) assign(section + '.' + nested[1], nested[2]); continue }
    const deep = line.match(/^ {4}([A-Za-z_][\w-]*):\s*(.*)$/)
    if (deep && section && subSection) { if (deep[2]) assign(section + '.' + subSection + '.' + deep[1], deep[2]); continue }
  }
  function assign (key, rawValue) {
    const value = rawValue.replace(/^["']|["']$/g, '').trim()
    if (key === 'name') out.name = value
    else if (key === 'description') out.description = value
    else if (key === 'version' || key === 'metadata.version' || key === 'metadata.builtin_skill_version') out.version = out.version || value
    else if (key === 'metadata.qwenpaw.emoji') out.emoji = value
  }
  if (!out.name) throw new Error('SKILL.md frontmatter 缺少 name')
  if (!out.description) throw new Error('SKILL.md frontmatter 缺少 description')
  return out
}

// ---------- 技能包读取与校验 ----------
export function loadOfficePack (packRoot) {
  const manifestPath = join(packRoot, 'office-pack.json')
  if (!existsSync(manifestPath)) throw new Error('办公技能包清单缺失：' + manifestPath)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  if (!Array.isArray(manifest.skills) || !manifest.skills.length) throw new Error('office-pack.json 未声明任何技能')
  const skills = manifest.skills.map(dir => {
    const skillDir = join(packRoot, dir)
    const skillMd = join(skillDir, 'SKILL.md')
    if (!existsSync(skillMd)) throw new Error(`技能 ${dir} 缺少 SKILL.md`)
    const frontmatter = parseSkillFrontmatter(readFileSync(skillMd, 'utf8'))
    if (frontmatter.name !== dir) throw new Error(`技能目录名 ${dir} 与 frontmatter name "${frontmatter.name}" 不一致`)
    return { dir, name: dir, frontmatter, hash: hashTree(skillDir) }
  })
  // 清单声明与磁盘目录双向一致（多出的目录视为打包事故）
  const onDisk = readdirSync(packRoot, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => e.name)
  const extra = onDisk.filter(d => !manifest.skills.includes(d))
  if (extra.length) throw new Error('office-pack.json 未登记的技能目录：' + extra.join(', '))
  return { manifest, skills, version: manifest.version }
}

// ---------- 同步状态 ----------
function loadState (workspace) {
  const path = join(workspace, STATE_FILE)
  if (!existsSync(path)) return { schema_version: 'office-pack-state.v1', pack_version: '', targets: {} }
  try {
    const state = JSON.parse(readFileSync(path, 'utf8'))
    if (state && state.schema_version === 'office-pack-state.v1' && state.targets && typeof state.targets === 'object') return state
  } catch { /* 损坏的状态文件按空处理，重新全量同步 */ }
  return { schema_version: 'office-pack-state.v1', pack_version: '', targets: {} }
}

function saveState (workspace, state) {
  writeJsonAtomic(join(workspace, STATE_FILE), state)
}

// 把一个技能同步到目标目录（池或工作区 skills/）。
// 返回 'installed' | 'updated' | 'unchanged' | 'user-modified' | 'conflict'
function syncSkillDir (skill, targetDir, targetState) {
  if (existsSync(targetDir)) {
    if (!targetState) return 'conflict' // 存在同名目录但我们没有同步记录：用户自建，绝不动
    if (hashTree(targetDir) !== targetState) return 'user-modified' // 同步后被用户改过：跳过并保留
    if (targetState === skill.hash) return 'unchanged'
    rmSync(targetDir, { recursive: true, force: true })
    copyTree(skill.sourceDir, targetDir)
    return 'updated'
  }
  copyTree(skill.sourceDir, targetDir)
  return 'installed'
}

// ---------- 清单合并 ----------
function readWorkspaceManifest (workspaceDir) {
  const path = join(workspaceDir, 'skill.json')
  if (!existsSync(path)) return { schema_version: WORKSPACE_MANIFEST_SCHEMA, version: 0, skills: {} }
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8'))
    if (parsed && typeof parsed === 'object' && parsed.skills && typeof parsed.skills === 'object') return parsed
  } catch { /* 损坏则重建骨架（与运行时调和一致） */ }
  return { schema_version: WORKSPACE_MANIFEST_SCHEMA, version: 0, skills: {} }
}

function ensureWorkspaceEntry (manifest, skill) {
  const existing = manifest.skills[skill.name]
  if (!existing || typeof existing !== 'object' || Array.isArray(existing)) {
    manifest.skills[skill.name] = {
      enabled: true,
      channels: ['all'],
      preload: false,
      source: 'customized',
      installed_from: INSTALLED_FROM,
    }
    return true
  }
  // 已有条目：尊重用户对 enabled/channels 的修改，仅补齐来源标记
  let changed = false
  if (existing.installed_from !== INSTALLED_FROM) { existing.installed_from = INSTALLED_FROM; changed = true }
  return changed
}

function bumpVersion (manifest) {
  manifest.version = Math.max((manifest.version || 0) + 1, Date.now())
}

// ---------- 预置主流程 ----------
export function provisionOfficeSkills ({ workspace, packRoot, log = console.log } = {}) {
  if (!workspace || !packRoot) throw new Error('provisionOfficeSkills 需要 workspace 与 packRoot 参数')
  const pack = loadOfficePack(packRoot)
  for (const skill of pack.skills) skill.sourceDir = join(packRoot, skill.dir)
  const state = loadState(workspace)
  state.targets = state.targets || {}
  const result = { pack: pack.manifest.name, version: pack.version, targets: [], installed: 0, updated: 0, unchanged: 0, skipped: [] }

  // 目标：技能池 + 全部智能体工作区（含尚未创建 skills/ 的 default）
  const poolDir = join(workspace, 'skill_pool')
  const targets = [{ kind: 'pool', label: '技能池', dir: poolDir }]
  const workspacesRoot = join(workspace, 'workspaces')
  if (existsSync(workspacesRoot)) {
    for (const entry of readdirSync(workspacesRoot, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const agentDir = join(workspacesRoot, entry.name)
      const isAgentWorkspace = entry.name === 'default' || existsSync(join(agentDir, 'skills')) || existsSync(join(agentDir, 'skill.json'))
      if (isAgentWorkspace) targets.push({ kind: 'workspace', label: entry.name, dir: agentDir })
    }
  }

  for (const target of targets) {
    const stateKey = target.kind === 'pool' ? 'pool' : 'workspaces/' + target.label
    const targetState = (state.targets[stateKey] = state.targets[stateKey] || {})
    const skillsDir = target.kind === 'pool' ? target.dir : join(target.dir, 'skills')
    mkdirSync(skillsDir, { recursive: true })
    let manifestChanged = false
    let manifest = null
    if (target.kind === 'pool') {
      manifest = existsSync(join(target.dir, 'skill.json'))
        ? safeJson(join(target.dir, 'skill.json'), { schema_version: POOL_MANIFEST_SCHEMA, version: 0, skills: {}, builtin_skill_names: [] })
        : { schema_version: POOL_MANIFEST_SCHEMA, version: 0, skills: {}, builtin_skill_names: [] }
      manifest.skills = manifest.skills || {}
      manifest.builtin_skill_names = manifest.builtin_skill_names || []
    } else {
      manifest = readWorkspaceManifest(target.dir)
    }

    for (const skill of pack.skills) {
      const targetDir = join(skillsDir, skill.dir)
      const outcome = syncSkillDir(skill, targetDir, targetState[skill.dir])
      if (outcome === 'installed' || outcome === 'updated') {
        targetState[skill.dir] = skill.hash
        result[outcome]++
        log(`  [office] ${skill.dir} v${skill.frontmatter.version || '1.0.0'} → ${stateKey}（${outcome === 'installed' ? '新装' : '更新'}）`)
      } else if (outcome === 'unchanged') {
        result.unchanged++
      } else {
        result.skipped.push(`${stateKey}/${skill.dir}:${outcome}`)
        log(`  [office] 跳过 ${skill.dir} @ ${stateKey}（${outcome === 'user-modified' ? '用户已修改，保留现场' : '用户自建同名技能，不覆盖'}）`)
        continue
      }
      if (target.kind === 'pool') {
        const existing = manifest.skills[skill.dir]
        const entryNeedsUpdate = outcome !== 'unchanged' ||
          !existing || typeof existing !== 'object' ||
          existing.description !== skill.frontmatter.description ||
          existing.installed_from !== INSTALLED_FROM
        if (entryNeedsUpdate) {
          manifest.skills[skill.dir] = {
            name: skill.dir,
            description: skill.frontmatter.description,
            version_text: skill.frontmatter.version || '',
            emoji: skill.frontmatter.emoji || '',
            commit_text: '',
            source: 'customized',
            protected: false,
            requirements: { require_bins: [], require_envs: [], require_mcps: [] },
            updated_at: new Date().toISOString(),
            external: false,
            installed_from: INSTALLED_FROM,
            ...(existing && typeof existing === 'object' ? { config: existing.config, tags: existing.tags, automation: existing.automation } : {}),
          }
          manifestChanged = true
        }
      } else {
        manifestChanged = ensureWorkspaceEntry(manifest, skill) || manifestChanged
        if (outcome !== 'unchanged') manifestChanged = true
      }
    }

    if (manifestChanged) {
      bumpVersion(manifest)
      writeJsonAtomic(join(target.dir, 'skill.json'), manifest)
    }
    result.targets.push(stateKey)
    // 办公回复规范：仅 default 工作区（用户对话的办公助手）
    if (target.kind === 'workspace' && target.label === 'default') {
      const promptChanged = ensureOfficePrompt(target.dir, targetState, log)
      if (promptChanged.file) log('  [office] 办公回复规范 OFFICE.md 已写入 default 工作区（375 字符：安全/精炼/交付/事实纪律）')
      if (promptChanged.config) log('  [office] system_prompt_files → OFFICE.md+SOUL.md+PROFILE.md（避免泛用 AGENTS.md 全文注入）')
    }
  }

  state.pack_version = pack.version
  saveState(workspace, state)
  log(`  [office] 办公技能包 v${pack.version} 预置完成：${pack.skills.length} 项 → ${result.targets.join('、')}；` +
    `新装 ${result.installed}，更新 ${result.updated}，无变化 ${result.unchanged}` + (result.skipped.length ? `，跳过 ${result.skipped.length}` : ''))
  return result
}

function safeJson (path, fallback) {
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8'))
    return parsed && typeof parsed === 'object' ? parsed : fallback
  } catch { return fallback }
}

// ---------- CLI ----------
// 用法：node provision-office-skills.mjs [--workspace <dir>] [--pack-root <dir>] [--check]
// --check：只校验技能包完整性（供发布门禁），不写任何文件。
const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (invokedDirectly) {
  const args = process.argv.slice(2)
  const argValue = flag => {
    const i = args.indexOf(flag)
    return i >= 0 && args[i + 1] ? args[i + 1] : null
  }
  const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
  const repoRoot = join(appRoot, '..', '..')
  const workspace = argValue('--workspace') || process.env.QWENPAW_WORKING_DIR || join(appRoot, 'workspace')
  const packRoot = argValue('--pack-root') || join(repoRoot, 'skills', 'office')

  if (args.includes('--check')) {
    try {
      const pack = loadOfficePack(packRoot)
      console.log(`办公技能包校验通过：${pack.manifest.name} v${pack.version}，${pack.skills.length} 项技能 frontmatter 合法。`)
    } catch (e) {
      console.error('办公技能包校验失败：' + e.message)
      process.exit(1)
    }
  } else {
    provisionOfficeSkills({ workspace, packRoot })
  }
}
