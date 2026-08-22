import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { matchesVersion, resolveRuntime, runtimeCandidates, runtimeEnvironment, runtimeLock } from './runtime-env.mjs'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const lock = runtimeLock()

assert.equal(lock.version, '2.1.0')
assert.equal(lock.ref, 'release/v2.1.0')
assert.match(lock.commit, /^[0-9a-f]{40}$/)
assert.equal(lock.runtime_dir, 'runtime/qwenpaw')
for (const file of ['setup-ai-os.ps1', 'setup-ai-os.sh']) assert.ok(existsSync(join(repoRoot, file)), `missing ${file}`)

assert.equal(matchesVersion('QwenPaw, version 2.1.0', '2.1.0'), true)
assert.equal(matchesVersion('QwenPaw, version 12.1.0', '2.1.0'), false)
assert.equal(matchesVersion('QwenPaw, version 2.1.1', '2.1.0'), false)

const fakeRoot = join(repoRoot, 'path with spaces', 'runtime')
const windowsCandidate = runtimeCandidates(fakeRoot, 'win32')[0]
const project = resolveRuntime({
  platform: 'win32',
  allowGlobal: false,
  root: fakeRoot,
  exists: path => path === windowsCandidate.command || path === windowsCandidate.python,
  probe: () => ({ ok: true, output: 'QwenPaw, version 2.1.0', error: '' }),
})
assert.equal(project.source, 'project')
assert.equal(project.command, windowsCandidate.command)
assert.equal(runtimeEnvironment(project, { PATH: 'existing' }).PYTHON, windowsCandidate.python)
assert.equal(runtimeEnvironment(project, { PATH: 'existing' }).QWENPAW_HOME, join(appRoot, 'workspace'))
assert.equal(runtimeEnvironment(project, { PATH: 'existing' }).QWENPAW_WORKING_DIR, join(appRoot, 'workspace'))
assert.ok(runtimeEnvironment(project, { PATH: 'existing' }).PATH.includes('path with spaces'))

const wrongVersion = resolveRuntime({
  platform: 'win32',
  allowGlobal: false,
  root: fakeRoot,
  exists: () => true,
  probe: () => ({ ok: true, output: 'QwenPaw, version 2.2.0', error: '' }),
})
assert.equal(wrongVersion.source, 'missing')
assert.equal(wrongVersion.remedy, '.\\setup-ai-os.ps1')

const powershell = readFileSync(join(repoRoot, 'setup-ai-os.ps1'), 'utf8')
const shell = readFileSync(join(repoRoot, 'setup-ai-os.sh'), 'utf8')
for (const source of [powershell, shell]) {
  assert.ok(source.includes('UV_CACHE_DIR'))
  assert.ok(source.includes('UV_PYTHON_INSTALL_DIR'))
  assert.ok(source.includes('UV_NO_MODIFY_PATH'))
  assert.ok(source.includes('qwenpaw.lock.json'))
}
assert.ok(powershell.includes('$Offline') && powershell.includes('UV_OFFLINE'))
assert.ok(shell.includes('AI_OS_OFFLINE') && shell.includes('UV_OFFLINE'))

console.log('项目运行时回归通过：精确版本、项目优先、全局回退、空格路径、幂等与离线缓存契约正常。')
