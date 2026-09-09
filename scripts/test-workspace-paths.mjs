import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, readFileSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const temp = mkdtempSync(join(tmpdir(), 'aios-workspace-'))
const root = join(temp, "中文 user's install")
const scripts = join(root, 'apps', 'zhizaoyunAIOS', 'scripts')
const workspace = join(root, 'apps', 'zhizaoyunAIOS', 'workspace')
const brand = join(root, 'plugins', 'aios-brand')
try {
  mkdirSync(scripts, { recursive: true })
  mkdirSync(join(brand, 'dist'), { recursive: true })
  copyFileSync(fileURLToPath(new URL('../apps/zhizaoyunAIOS/scripts/ensure-workspace.mjs', import.meta.url)), join(scripts, 'ensure-workspace.mjs'))
  writeFileSync(join(brand, 'plugin.json'), JSON.stringify({ version: '1' }))
  writeFileSync(join(brand, 'dist', 'index.js'), 'version-one')
  for (const id of ['custom-user-plugin', 'zhiyun-auth']) {
    mkdirSync(join(workspace, 'plugins', id), { recursive: true })
    writeFileSync(join(workspace, 'plugins', id, 'sentinel'), 'user-data')
  }
  const run = () => {
    const result = spawnSync(process.execPath, [join(scripts, 'ensure-workspace.mjs')], { cwd: root, encoding: 'utf8' })
    assert.equal(result.status, 0, result.stderr || 'Workspace initialization crashed')
  }
  run(); run()
  assert.equal(readFileSync(join(workspace, 'plugins', 'aios-brand', 'dist', 'index.js'), 'utf8'), 'version-one')
  writeFileSync(join(brand, 'plugin.json'), JSON.stringify({ version: '2' }))
  writeFileSync(join(brand, 'dist', 'index.js'), 'version-two')
  run()
  assert.equal(readFileSync(join(workspace, 'plugins', 'aios-brand', 'dist', 'index.js'), 'utf8'), 'version-two')
  assert.equal(readFileSync(join(workspace, 'plugins', 'custom-user-plugin', 'sentinel'), 'utf8'), 'user-data')
  const backup = readdirSync(workspace).find(x => x.startsWith('plugins.legacy-backup-'))
  assert.ok(backup && existsSync(join(workspace, backup, 'zhiyun-auth', 'sentinel')))
  console.log('Workspace Chinese/space/apostrophe paths: first install, repeat, upgrade and recoverable legacy migration passed')
} finally {
  assert.ok(resolve(temp).startsWith(resolve(tmpdir()) + sep + 'aios-workspace-'))
  rmSync(temp, { recursive: true, force: true })
}
