// 办公专属默认技能包预置测试（aios-office 分支）
// 覆盖：首次预置（池+工作区+默认启用）、幂等重跑、用户自建同名技能保护、
// 用户修改保护、清单条目保留、ensure-workspace 挂接、CLI --check、frontmatter 校验。
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const scriptsRoot = fileURLToPath(new URL('.', import.meta.url))
const repoRoot = join(scriptsRoot, '..', '..', '..')
const packRoot = join(repoRoot, 'skills', 'office')
const { provisionOfficeSkills, parseSkillFrontmatter, loadOfficePack } = await import(pathToFileURL(join(scriptsRoot, 'provision-office-skills.mjs')).href)

const temp = mkdtempSync(join(tmpdir(), 'aios-office-pack-'))
const quiet = () => {}
try {
  // ---------- 0) 技能包本体 ----------
  const pack = loadOfficePack(packRoot)
  assert.equal(pack.manifest.name, 'aios-office-pack')
  assert.equal(pack.skills.length, 11, '办公技能包必须包含 11 项技能')
  assert.deepEqual(pack.skills.map(s => s.dir).sort(),
    ['office-browser', 'office-computer', 'office-content', 'office-excel', 'office-file-reader',
      'office-image-search', 'office-ocr', 'office-pdf', 'office-ppt', 'office-research', 'office-word'],
    '十一项能力清单必须与文档一致')

  // ---------- frontmatter 解析 ----------
  assert.equal(parseSkillFrontmatter('---\nname: a\ndescription: "d"\n---\n# x').name, 'a')
  assert.throws(() => parseSkillFrontmatter('---\ndescription: d\n---\n'), /缺少 name/)
  assert.throws(() => parseSkillFrontmatter('---\nname: a\n---\n'), /缺少 description/)
  assert.throws(() => parseSkillFrontmatter('no frontmatter'), /缺少 frontmatter 起始/)

  // ---------- 1) 首次预置：池 + default 工作区，默认启用 ----------
  const workspace = join(temp, "中文 user's workspace")
  mkdirSync(join(workspace, 'workspaces', 'default'), { recursive: true })
  // 预置一条用户已有技能清单条目：预置后必须原样保留
  writeFileSync(join(workspace, 'workspaces', 'default', 'skill.json'), JSON.stringify({
    schema_version: 'workspace-skill-manifest.v1',
    version: 7,
    skills: { 'my-own-skill': { enabled: true, channels: ['console'] } },
  }))
  const first = provisionOfficeSkills({ workspace, packRoot, log: quiet })
  assert.equal(first.installed, 22, '11 技能 × (技能池 + default 工作区) 全部新装')
  for (const dir of pack.skills.map(s => s.dir)) {
    assert.ok(existsSync(join(workspace, 'skill_pool', dir, 'SKILL.md')), `池缺少 ${dir}`)
    assert.ok(existsSync(join(workspace, 'workspaces', 'default', 'skills', dir, 'SKILL.md')), `工作区缺少 ${dir}`)
  }
  const poolManifest = JSON.parse(readFileSync(join(workspace, 'skill_pool', 'skill.json'), 'utf8'))
  assert.equal(poolManifest.schema_version, 'skill-pool-manifest.v1')
  assert.ok(poolManifest.skills['office-ppt'].description.length > 10, '池条目应有 description')
  assert.equal(poolManifest.skills['office-ppt'].installed_from, 'office-pack')
  const wsManifest = JSON.parse(readFileSync(join(workspace, 'workspaces', 'default', 'skill.json'), 'utf8'))
  assert.equal(wsManifest.schema_version, 'workspace-skill-manifest.v1')
  assert.equal(wsManifest.skills['office-ppt'].enabled, true, '办公技能必须默认启用')
  assert.deepEqual(wsManifest.skills['office-ppt'].channels, ['all'])
  assert.equal(wsManifest.skills['my-own-skill'].channels[0], 'console', '用户既有条目不得被改动')

  // ---------- 2) 幂等重跑：全部 unchanged，清单 version 不变 ----------
  const poolVersionBefore = poolManifest.version
  const wsVersionBefore = wsManifest.version
  const second = provisionOfficeSkills({ workspace, packRoot, log: quiet })
  assert.equal(second.installed, 0)
  assert.equal(second.updated, 0)
  assert.equal(second.unchanged, 22, '重跑全部无变化')
  assert.equal(second.skipped.length, 0)
  assert.equal(JSON.parse(readFileSync(join(workspace, 'skill_pool', 'skill.json'), 'utf8')).version, poolVersionBefore, '池清单未被重写')
  assert.equal(JSON.parse(readFileSync(join(workspace, 'workspaces', 'default', 'skill.json'), 'utf8')).version, wsVersionBefore, '工作区清单未被重写')

  // ---------- 3) 用户自建同名技能（无预置记录）：不覆盖 ----------
  const freshWorkspace = join(temp, 'fresh-workspace')
  const userPoolSkill = join(freshWorkspace, 'skill_pool', 'office-ppt')
  mkdirSync(userPoolSkill, { recursive: true })
  writeFileSync(join(userPoolSkill, 'SKILL.md'), '---\nname: office-ppt\ndescription: 用户自己的技能\n---\n')
  mkdirSync(join(freshWorkspace, 'workspaces', 'default'), { recursive: true })
  const third = provisionOfficeSkills({ workspace: freshWorkspace, packRoot, log: quiet })
  assert.ok(third.skipped.some(s => s.startsWith('pool/office-ppt:conflict')), '用户自建同名技能应报 conflict 跳过')
  assert.ok(readFileSync(join(userPoolSkill, 'SKILL.md'), 'utf8').includes('用户自己的技能'), '用户内容必须原样保留')
  const freshPool = JSON.parse(readFileSync(join(freshWorkspace, 'skill_pool', 'skill.json'), 'utf8'))
  assert.ok(!freshPool.skills['office-ppt'], '冲突技能不得写入池清单')

  // ---------- 4) 用户修改已预置技能：保留现场 ----------
  const modifiedFile = join(workspace, 'workspaces', 'default', 'skills', 'office-excel', 'SKILL.md')
  const original = readFileSync(modifiedFile, 'utf8')
  writeFileSync(modifiedFile, original + '\n<!-- 用户批注 -->\n')
  const fourth = provisionOfficeSkills({ workspace, packRoot, log: quiet })
  assert.ok(fourth.skipped.some(s => s.startsWith('workspaces/default/office-excel:user-modified')), '用户修改过的技能应跳过更新')
  assert.ok(readFileSync(modifiedFile, 'utf8').includes('用户批注'), '用户修改必须保留')
  // 工作区清单条目仍存在且启用
  const afterMod = JSON.parse(readFileSync(join(workspace, 'workspaces', 'default', 'skill.json'), 'utf8'))
  assert.equal(afterMod.skills['office-excel'].enabled, true)

  // ---------- 5) 版本升级：未被动过的技能被更新 ----------
  writeFileSync(modifiedFile, original) // 还原，模拟未被用户修改
  // 直接改源技能内容等价于包版本变化：复制一份包并修改其中 office-word
  const packCopy = join(temp, 'pack-copy')
  mkdirSync(packCopy, { recursive: true })
  for (const entry of readdirSync(packRoot, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      mkdirSync(join(packCopy, entry.name), { recursive: true })
      writeFileSync(join(packCopy, entry.name, 'SKILL.md'), readFileSync(join(packRoot, entry.name, 'SKILL.md')))
    } else writeFileSync(join(packCopy, entry.name), readFileSync(join(packRoot, entry.name)))
  }
  const wordMd = join(packCopy, 'office-word', 'SKILL.md')
  writeFileSync(wordMd, readFileSync(wordMd, 'utf8') + '\n<!-- v1.0.1 -->\n')
  const fifth = provisionOfficeSkills({ workspace, packRoot: packCopy, log: quiet })
  assert.equal(fifth.updated, 2, 'office-word 在池与工作区两处被更新')
  assert.ok(readFileSync(join(workspace, 'workspaces', 'default', 'skills', 'office-word', 'SKILL.md'), 'utf8').includes('v1.0.1'))

  // ---------- 6) 新增智能体工作区：下次启动自动覆盖 ----------
  mkdirSync(join(workspace, 'workspaces', 'agent-002', 'skills'), { recursive: true })
  writeFileSync(join(workspace, 'workspaces', 'agent-002', 'skill.json'), JSON.stringify({
    schema_version: 'workspace-skill-manifest.v1', version: 1, skills: {},
  }))
  provisionOfficeSkills({ workspace, packRoot, log: quiet })
  const agent002 = JSON.parse(readFileSync(join(workspace, 'workspaces', 'agent-002', 'skill.json'), 'utf8'))
  assert.equal(agent002.skills['office-ppt'].enabled, true, '新工作区同样默认启用')
  // 用户禁用的技能保持禁用（尊重用户选择）
  agent002.skills['office-ppt'].enabled = false
  writeFileSync(join(workspace, 'workspaces', 'agent-002', 'skill.json'), JSON.stringify(agent002))
  provisionOfficeSkills({ workspace, packRoot, log: quiet })
  const agent002After = JSON.parse(readFileSync(join(workspace, 'workspaces', 'agent-002', 'skill.json'), 'utf8'))
  assert.equal(agent002After.skills['office-ppt'].enabled, false, '用户禁用不得被预置强行打开')

  // ---------- 7) ensure-workspace 挂接（单机启动链路） ----------
  const hookRoot = join(temp, 'hook-run')
  const hookScripts = join(hookRoot, 'apps', 'zhizaoyunAIOS', 'scripts')
  const hookWorkspace = join(hookRoot, 'apps', 'zhizaoyunAIOS', 'workspace')
  const hookPack = join(hookRoot, 'skills', 'office')
  mkdirSync(hookScripts, { recursive: true })
  mkdirSync(join(hookWorkspace, 'workspaces', 'default'), { recursive: true })
  // 复制脚本与技能包（相对路径解析：ensure-workspace 从 appRoot/../.. 找 skills/office）
  for (const f of ['ensure-workspace.mjs', 'provision-office-skills.mjs']) {
    writeFileSync(join(hookScripts, f), readFileSync(join(scriptsRoot, f)))
  }
  mkdirSync(hookPack, { recursive: true })
  writeFileSync(join(hookPack, 'office-pack.json'), readFileSync(join(packRoot, 'office-pack.json')))
  for (const s of pack.skills) {
    mkdirSync(join(hookPack, s.dir), { recursive: true })
    writeFileSync(join(hookPack, s.dir, 'SKILL.md'), readFileSync(join(packRoot, s.dir, 'SKILL.md')))
  }
  const hookRun = spawnSync(process.execPath, [join(hookScripts, 'ensure-workspace.mjs')], { encoding: 'utf8' })
  assert.equal(hookRun.status, 0, hookRun.stderr || 'ensure-workspace 挂接后启动失败')
  assert.ok(existsSync(join(hookWorkspace, 'workspaces', 'default', 'skills', 'office-ppt', 'SKILL.md')), 'ensure-workspace 应完成技能预置')
  assert.equal(JSON.parse(readFileSync(join(hookWorkspace, 'workspaces', 'default', 'skill.json'), 'utf8')).skills['office-ppt'].enabled, true)

  // 缺少技能包时静默跳过、不报错（裁剪安装/单文件拷贝场景）
  rmSync(hookPack, { recursive: true, force: true })
  const hookRun2 = spawnSync(process.execPath, [join(hookScripts, 'ensure-workspace.mjs')], { encoding: 'utf8' })
  assert.equal(hookRun2.status, 0, '技能包缺失不应导致启动失败')

  // ---------- 8) CLI --check（发布门禁用） ----------
  const check = spawnSync(process.execPath, [join(scriptsRoot, 'provision-office-skills.mjs'), '--check'], { encoding: 'utf8' })
  assert.equal(check.status, 0, check.stderr || '--check 必须通过')

  // ---------- 9) 办公回复规范 OFFICE.md 与注入列表精简（v1.3.0） ----------
  const promptWorkspace = join(temp, 'prompt-ws')
  const promptDefault = join(promptWorkspace, 'workspaces', 'default')
  mkdirSync(promptDefault, { recursive: true })
  writeFileSync(join(promptDefault, 'agent.json'), JSON.stringify({
    system_prompt_files: ['AGENTS.md', 'SOUL.md', 'PROFILE.md'],
    persona_extra: '用户的其他配置',
  }))
  const pr1 = provisionOfficeSkills({ workspace: promptWorkspace, packRoot, log: quiet })
  assert.ok(existsSync(join(promptDefault, 'OFFICE.md')), 'default 工作区应写入 OFFICE.md')
  const officeMd = readFileSync(join(promptDefault, 'OFFICE.md'), 'utf8')
  assert.ok(officeMd.includes('回复精炼') && officeMd.includes('绝不覆盖用户原件'), 'OFFICE.md 应含回复与交付纪律')
  assert.ok(officeMd.length <= 600, 'OFFICE.md 必须精简（≤600 字符，每轮注入成本）')
  const agentCfg = JSON.parse(readFileSync(join(promptDefault, 'agent.json'), 'utf8'))
  assert.deepEqual(agentCfg.system_prompt_files, ['OFFICE.md', 'SOUL.md', 'PROFILE.md'], '默认三件套应替换为 OFFICE 注入列表')
  assert.equal(agentCfg.persona_extra, '用户的其他配置', 'agent.json 其他字段必须保留')
  // 幂等：重跑不变
  provisionOfficeSkills({ workspace: promptWorkspace, packRoot, log: quiet })
  assert.equal(readFileSync(join(promptDefault, 'agent.json'), 'utf8'), JSON.stringify(agentCfg, null, 2) + '\n', '注入列表重跑不漂移')
  // 用户自定义注入列表：不动
  agentCfg.system_prompt_files = ['MY.md']
  writeFileSync(join(promptDefault, 'agent.json'), JSON.stringify(agentCfg))
  provisionOfficeSkills({ workspace: promptWorkspace, packRoot, log: quiet })
  assert.deepEqual(JSON.parse(readFileSync(join(promptDefault, 'agent.json'), 'utf8')).system_prompt_files, ['MY.md'], '用户自定义列表不得被改')
  // 用户修改 OFFICE.md：保留现场
  writeFileSync(join(promptDefault, 'OFFICE.md'), officeMd + '\n<!-- 用户批注 -->\n')
  provisionOfficeSkills({ workspace: promptWorkspace, packRoot, log: quiet })
  assert.ok(readFileSync(join(promptDefault, 'OFFICE.md'), 'utf8').includes('用户批注'), '用户修改的 OFFICE.md 必须保留')

  console.log('办公技能包预置测试通过：首装/幂等/用户保护/版本升级/新工作区/启动挂接/CLI 校验/办公回复规范。')
} finally {
  assert.ok(temp.includes(join('aios-office-pack-')))
  rmSync(temp, { recursive: true, force: true })
}
