import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const embedded = join(root, 'apps', 'qwenpaw-embedded')
const scripts = join(embedded, 'scripts')

for (const removed of [
  'apps/enterprise/package.json',
  'apps/enterprise/server/index.js',
  'pawapps/zhiyun-orders/plugin.json',
  'pawapps/_shared/zhiyun_workspace.py',
  'apps/qwenpaw-embedded/scripts/cleanup-legacy.py',
  'apps/qwenpaw-embedded/scripts/set-logo.py',
  'apps/qwenpaw-embedded/scripts/verify-r0.mjs',
  'apps/qwenpaw-embedded/scripts/verify-s0.mjs',
]) {
  assert.equal(existsSync(join(root, removed)), false, `legacy source must be removed: ${removed}`)
}

const qwenpawLock = JSON.parse(readFileSync(join(embedded, 'qwenpaw.lock.json'), 'utf8'))
assert.equal(qwenpawLock.schema_version, 1)
assert.equal(qwenpawLock.package, 'qwenpaw')
assert.equal(qwenpawLock.version, '2.1.0')
assert.equal(qwenpawLock.ref, 'release/v2.1.0', 'QwenPaw must stay pinned to release/v2.1.0')
assert.match(qwenpawLock.commit, /^[0-9a-f]{40}$/, 'QwenPaw must use a full commit SHA')
const pawapps = JSON.parse(readFileSync(join(embedded, 'pawapps.lock.json'), 'utf8'))
assert.equal(pawapps.schema_version, 1)
assert.ok(pawapps.apps.length >= 2, 'release must include Data Studio and Order Studio')
assert.equal(new Set(pawapps.apps.map(app => app.id)).size, pawapps.apps.length)
for (const app of pawapps.apps) assert.match(app.commit, /^[0-9a-f]{40}$/, `${app.id} must use a full commit SHA`)

const catalog = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'app_catalog.json'), 'utf8'))
const catalogById = new Map(catalog.apps.map(app => [app.app_id, app]))
for (const app of pawapps.apps) {
  const entry = catalogById.get(app.id)
  assert.ok(entry, `${app.id} must exist in App Discovery`)
  assert.equal(entry.install_status, 'installed', `${app.id} must be reported as installed`)
  assert.equal(entry.health, 'available', `${app.id} must be reported as available`)
  assert.ok(entry.route, `${app.id} must expose a route`)
}

for (const pluginId of ['zhiyun-app-discovery', 'zhiyun-audit', 'zhiyun-data-core', 'zhiyun-logo']) {
  const manifest = JSON.parse(readFileSync(join(root, 'plugins', pluginId, 'plugin.json'), 'utf8'))
  assert.equal(catalogById.get(pluginId)?.version, manifest.version, `${pluginId} catalog version must match plugin.json`)
}

const start = readFileSync(join(scripts, 'start.mjs'), 'utf8')
assert.ok(start.includes('for (const app of externalApps)'), 'launcher must install every locked PawApp')
assert.ok(start.includes('cleanup-legacy.mjs'), 'launcher must use the Desktop-compatible cleanup')
assert.ok(!start.includes('cleanup-legacy.py'), 'launcher must not depend on Python cleanup')
assert.ok(!start.includes('8390'), 'launcher must not start the retired service')

const sync = readFileSync(join(scripts, 'sync-pawapps.mjs'), 'utf8')
assert.ok(sync.includes("'.pawapp-commit'"), 'sync must use a materialization marker')
assert.ok(sync.includes("rmSync(join(staging, '.git')"), 'sync must remove Git metadata before install')
const cleanup = readFileSync(join(scripts, 'cleanup-legacy.mjs'), 'utf8')
assert.ok(cleanup.includes('QWENPAW_WORKING_DIR') && cleanup.includes('COPAW_WORKING_DIR'), 'cleanup must follow the QwenPaw working directory contract')
for (const pluginId of ['cospaw', 'ai_decision', 'team_chat', 'qwenpaw-creator']) {
  assert.ok(cleanup.includes(pluginId), `cleanup must quarantine incompatible plugin: ${pluginId}`)
}
assert.ok(existsSync(join(root, 'plugins', 'zhiyun-logo', 'assets', 'default-logo.png')), 'packaged default logo is missing')

const allowedToolTypes = new Set(['file', 'internal', 'network', 'shell'])
for (const pluginFile of [
  join(root, 'plugins', 'zhiyun-app-discovery', 'app_discovery_plugin.py'),
  join(root, 'plugins', 'zhiyun-data-core', 'data_core_plugin.py'),
]) {
  const source = readFileSync(pluginFile, 'utf8')
  for (const match of source.matchAll(/tool_type="([^"]+)"/g)) {
    assert.ok(allowedToolTypes.has(match[1]), `invalid QwenPaw governance type ${match[1]} in ${pluginFile}`)
  }
}

for (const entry of ['setup-ai-os.ps1', 'setup-ai-os.sh', 'start-ai-os.cmd', 'start-ai-os.sh', 'diagnose-ai-os.cmd', 'diagnose-ai-os.sh', 'set-ai-os-logo.cmd', 'set-ai-os-logo.sh', 'check-ai-os.cmd', 'check-ai-os.sh']) {
  assert.ok(existsSync(join(root, entry)), `missing cross-platform entry: ${entry}`)
}

const commands = [
  [process.execPath, [join(root, 'scripts', 'verify-project-plan.mjs')]],
  [process.execPath, ['--check', join(scripts, 'start.mjs')]],
  [process.execPath, ['--check', join(scripts, 'runtime-env.mjs')]],
  [process.execPath, ['--check', join(scripts, 'sync-pawapps.mjs')]],
  [process.execPath, ['--check', join(scripts, 'doctor.mjs')]],
  [process.execPath, ['--check', join(scripts, 'cleanup-legacy.mjs')]],
  [process.execPath, ['--check', join(scripts, 'set-logo.mjs')]],
  [process.execPath, ['--check', join(scripts, 'health-report.mjs')]],
  [process.execPath, [join(scripts, 'health-report.mjs'), '--check']],
  [process.execPath, [join(scripts, 'verify-health-report.mjs')]],
  [process.execPath, [join(scripts, 'set-logo.mjs'), '--check']],
  [process.execPath, [join(scripts, 'sync-pawapps.mjs'), '--check']],
  [process.execPath, [join(scripts, 'verify-deployment.mjs')]],
  [process.execPath, [join(scripts, 'verify-runtime.mjs')]],
  [process.execPath, [join(scripts, 'verify-maintenance.mjs')]],
]
for (const [command, args] of commands) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' })
  assert.equal(result.status, 0, `release check failed: ${command} ${args.join(' ')}`)
}

const materialize = spawnSync(process.execPath, [join(scripts, 'sync-pawapps.mjs')], { cwd: root, stdio: 'inherit' })
assert.equal(materialize.status, 0, 'locked PawApps must materialize from GitHub')

function pythonFiles (directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? pythonFiles(path) : (entry.name.endsWith('.py') ? [path] : [])
  })
}

for (const app of pawapps.apps) {
  const appRoot = join(embedded, 'runtime', 'pawapps', app.install_dir)
  const manifest = JSON.parse(readFileSync(join(appRoot, 'plugin.json'), 'utf8'))
  const entry = catalogById.get(app.id)
  assert.equal(manifest.id, app.id, `${app.id} manifest ID mismatch`)
  assert.equal(manifest.version, entry.version, `${app.id} catalog version must match materialized manifest`)
  assert.equal(manifest.meta?.pawapp?.entry_page, entry.route, `${app.id} route must match materialized manifest`)
  assert.equal(readFileSync(join(appRoot, '.pawapp-commit'), 'utf8').trim(), app.commit, `${app.id} marker must match lock`)
  assert.equal(existsSync(join(appRoot, '.git')), false, `${app.id} install source must not contain Git metadata`)
  for (const pluginFile of pythonFiles(join(appRoot, 'backend'))) {
    const source = readFileSync(pluginFile, 'utf8')
    for (const match of source.matchAll(/tool_type="([^"]+)"/g)) {
      assert.ok(allowedToolTypes.has(match[1]), `invalid QwenPaw governance type ${match[1]} in ${pluginFile}`)
    }
  }
}

const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
for (const plugin of ['zhiyun-app-discovery', 'zhiyun-audit', 'zhiyun-data-core']) {
  const result = spawnSync(python, ['-m', 'unittest', 'discover', '-s', join(root, 'plugins', plugin), '-p', 'test*.py', '-v'], { cwd: join(root, 'plugins', plugin), stdio: 'inherit' })
  assert.equal(result.status, 0, `Python tests failed: ${plugin}`)
}

for (const app of pawapps.apps) {
  const appRoot = join(embedded, 'runtime', 'pawapps', app.install_dir)
  const result = spawnSync(python, ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test*.py', '-v'], { cwd: appRoot, stdio: 'inherit' })
  assert.equal(result.status, 0, `Python tests failed: ${app.id}`)
}

console.log('AI-OS 发布门禁通过：纯QwenPaw架构、跨平台启动、版本锁、系统插件和全部锁定PawApp测试均正常。')
