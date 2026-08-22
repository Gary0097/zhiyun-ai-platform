import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const scripts = dirname(fileURLToPath(import.meta.url))
const root = join(scripts, '..', '..', '..')
const defaultLogo = join(root, 'plugins', 'zhiyun-logo', 'assets', 'default-logo.png')
const temp = mkdtempSync(join(tmpdir(), 'zhiyun-maintenance-'))
const env = { ...process.env, QWENPAW_WORKING_DIR: temp }

function run (script, args = []) {
  const result = spawnSync(process.execPath, [join(scripts, script), ...args], { cwd: root, env, encoding: 'utf8' })
  if (result.stdout) process.stdout.write(result.stdout)
  if (result.stderr) process.stderr.write(result.stderr)
  assert.equal(result.status, 0, `${script} failed`)
}

try {
  run('set-logo.mjs', [defaultLogo])
  const logoConfig = JSON.parse(readFileSync(join(temp, 'branding', 'logo.json'), 'utf8'))
  assert.equal(logoConfig.mime, 'image/png')
  assert.ok(existsSync(logoConfig.path))
  run('set-logo.mjs', ['--reset'])
  assert.equal(existsSync(join(temp, 'branding', 'logo.json')), false)

  const workspace = join(temp, 'workspaces', 'default')
  const disabledIds = ['zhiyun-orders', 'cospaw', 'ai_decision', 'team_chat', 'qwenpaw-creator']
  for (const pluginId of [...disabledIds, 'user-kept-plugin']) {
    mkdirSync(join(temp, 'plugins', pluginId), { recursive: true })
  }
  mkdirSync(workspace, { recursive: true })
  writeFileSync(join(temp, 'config.json'), JSON.stringify({ agents: { profiles: { default: { workspace_dir: workspace } } } }), 'utf8')
  writeFileSync(join(workspace, 'agent.json'), JSON.stringify({ tools: { builtin_tools: { enterprise_platform_status: { enabled: true }, safe_tool: { enabled: true } } } }), 'utf8')
  run('cleanup-legacy.mjs')

  const agent = JSON.parse(readFileSync(join(workspace, 'agent.json'), 'utf8'))
  assert.equal(agent.tools.builtin_tools.enterprise_platform_status, undefined)
  assert.ok(agent.tools.builtin_tools.safe_tool)
  for (const pluginId of disabledIds) {
    assert.equal(existsSync(join(temp, 'plugins', pluginId)), false, `${pluginId} should be disabled`)
  }
  assert.ok(existsSync(join(temp, 'plugins', 'user-kept-plugin')), 'unknown user plugins must be preserved')
  const backups = readdirSync(join(temp, 'disabled_plugins'))
  for (const pluginId of disabledIds) {
    assert.ok(backups.some(name => name.startsWith(`${pluginId}-`)), `${pluginId} backup is missing`)
  }
} finally {
  rmSync(temp, { recursive: true, force: true })
}

console.log('维护脚本回归通过：Logo、工作目录、遗留Tool和不兼容插件的可恢复清理正常。')
