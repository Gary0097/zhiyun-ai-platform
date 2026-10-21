// ZCode 默认办公技能桥接测试（aios-office 分支）
// 覆盖：版本目录择新、SKILL.md 探测、config.json skill_paths 合并幂等、
// 用户自配条目保留、未安装跳过、CLI --check、ensure-workspace 挂接。
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const scriptsRoot = fileURLToPath(new URL('.', import.meta.url))
const { linkZcodeSkills, latestSkillsDir } = await import(pathToFileURL(join(scriptsRoot, 'link-zcode-skills.mjs')).href)

const temp = mkdtempSync(join(tmpdir(), 'aios-zcode-link-'))
const quiet = () => {}
try {
  // ---------- 1) 版本择新与 SKILL.md 探测 ----------
  const zcodeRoot = join(temp, 'zcode-plugins-official')
  const mkPlugin = (id, versions) => {
    for (const [v, skills] of Object.entries(versions)) {
      for (const s of skills) {
        mkdirSync(join(zcodeRoot, id, v, 'skills', s), { recursive: true })
        writeFileSync(join(zcodeRoot, id, v, 'skills', s, 'SKILL.md'), `---\nname: ${s}\ndescription: test\n---\n# ${s}\n`)
      }
    }
  }
  mkPlugin('presentations', { '0.1.6': ['pptx-old'], '0.1.7': ['pptx'] })
  mkPlugin('spreadsheets', { '0.1.7': ['xlsx'] })
  mkPlugin('documents', { '0.1.8': ['docx'] })
  mkdirSync(join(zcodeRoot, 'empty-plugin', '0.1.0', 'skills'), { recursive: true }) // 无 SKILL.md 的插件
  assert.equal(latestSkillsDir(join(zcodeRoot, 'presentations')), join(zcodeRoot, 'presentations', '0.1.7', 'skills'), '必须选最新版本')
  assert.equal(latestSkillsDir(join(zcodeRoot, 'empty-plugin')), null, '无 SKILL.md 的版本必须跳过')

  // ---------- 2) 桥接合并 config.json（保留用户条目 + 幂等） ----------
  const workspace = join(temp, 'workspace')
  mkdirSync(workspace, { recursive: true })
  writeFileSync(join(workspace, 'config.json'), JSON.stringify({
    language: 'zh', skill_paths: ['/user/own/skills'],
  }))
  const first = linkZcodeSkills({ workspace, zcodeRoot, pluginIds: ['presentations', 'spreadsheets', 'documents', 'empty-plugin'], log: quiet })
  assert.equal(first.status, 'linked')
  assert.equal(first.added.length, 3, 'empty-plugin 不产生条目')
  const cfg = JSON.parse(readFileSync(join(workspace, 'config.json'), 'utf8'))
  assert.equal(cfg.skill_paths[0], '/user/own/skills', '用户自配条目必须保留')
  assert.ok(cfg.skill_paths.includes(join(zcodeRoot, 'presentations', '0.1.7', 'skills')))
  assert.equal(cfg.language, 'zh', '其余配置字段不受影响')

  const second = linkZcodeSkills({ workspace, zcodeRoot, pluginIds: ['presentations', 'spreadsheets', 'documents'], log: quiet })
  assert.equal(second.status, 'up-to-date', '重跑幂等')

  // ---------- 3) 未安装 ZCode：静默跳过 ----------
  const emptyWorkspace = join(temp, 'ws2')
  mkdirSync(emptyWorkspace, { recursive: true })
  assert.equal(linkZcodeSkills({ workspace: emptyWorkspace, zcodeRoot: join(temp, 'no-such-root'), log: quiet }).status, 'not-installed')
  assert.equal(linkZcodeSkills({ workspace: emptyWorkspace, zcodeRoot: join(temp, 'no-such-root'), log: quiet }).paths.length, 0)

  // ---------- 4) CLI --check 与启动挂接 ----------
  const check = spawnSync(process.execPath, [join(scriptsRoot, 'link-zcode-skills.mjs'), '--check'], { encoding: 'utf8' })
  assert.equal(check.status, 0, check.stderr || '--check 必须通过')
  const ensureSrc = readFileSync(join(scriptsRoot, 'ensure-workspace.mjs'), 'utf8')
  assert.ok(ensureSrc.includes('link-zcode-skills'), 'ensure-workspace.mjs must hook the zcode bridge')

  console.log('ZCode 技能桥接测试通过：版本择新/条目合并幂等/用户条目保留/未装跳过/CLI 校验/启动挂接。')
} finally {
  assert.ok(temp.includes(join('aios-zcode-link-')))
  rmSync(temp, { recursive: true, force: true })
}
