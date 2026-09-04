// 智造云 AIOS 2.2.0 发布门禁（极简形态：无捆绑业务应用）
// 检查：跨平台入口完整性、版本锁一致性、脚本语法、控制台品牌化、
// 打包/清理脚本自检。业务应用已剥离，其验收由各应用独立仓库自行承担。
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const embedded = join(root, 'apps', 'zhizaoyunAIOS')
const scripts = join(embedded, 'scripts')

// 1) 版本锁一致性（唯一运行时 = QwenPaw 2.2.0）
const qwenpawLock = JSON.parse(readFileSync(join(embedded, 'qwenpaw.lock.json'), 'utf8'))
assert.equal(qwenpawLock.version, '2.2.0')
assert.equal(qwenpawLock.ref, 'v2.2.0')
assert.ok(!existsSync(join(embedded, 'pawapps.lock.json')), '2.2.0 极简形态不应存在 PawApp 锁')

// 2) 跨平台入口完整性（单机 8088 + Hub 8000）
for (const entry of [
  'setup-ai-os.ps1', 'setup-ai-os.sh', 'setup-hub.ps1', 'setup-hub.sh',
  'start-ai-os.cmd', 'start-ai-os.sh', 'start-hub.cmd', 'start-hub.sh',
  'diagnose-ai-os.cmd', 'diagnose-ai-os.sh', 'install-oneclick.cmd', 'install-oneclick.sh',
]) {
  assert.ok(existsSync(join(root, entry)), `missing cross-platform entry: ${entry}`)
}

// 3) 登录体系：原生认证必须默认启用（QWENPAW_AUTH_ENABLED）
const start = readFileSync(join(scripts, 'start.mjs'), 'utf8')
assert.ok(start.includes('QWENPAW_AUTH_ENABLED'), 'start.mjs must enable native console auth')
assert.ok(!start.includes('plugin'), 'start.mjs must not install bundled plugins (2.2.0 slim)')

// 4) 业务应用剥离后不得残留脚本引用
for (const banned of ['sync-pawapps', 'pawapp-materialized', 'seed-builtin-agents', 'health-report', 'set-logo', 'cleanup-legacy']) {
  assert.ok(!existsSync(join(scripts, banned + '.mjs')), `leftover business script: ${banned}.mjs`)
}
assert.ok(!existsSync(join(root, 'plugins')), 'vendored plugins/ must be removed in 2.2.0 slim')

// 5) 脚本检查（语法 + 自检）
const commands = [
  [process.execPath, ['--check', join(scripts, 'start.mjs')]],
  [process.execPath, ['--check', join(scripts, 'runtime-env.mjs')]],
  [process.execPath, ['--check', join(scripts, 'doctor.mjs')]],
  [process.execPath, ['--check', join(scripts, 'ensure-workspace.mjs')]],
  [process.execPath, ['--check', join(scripts, 'patch-console-ui.mjs')]],
  [process.execPath, [join(scripts, 'verify-runtime.mjs')]],
  [process.execPath, [join(scripts, 'patch-console-ui.mjs'), '--check']],
  [process.execPath, [join(root, 'scripts', 'release-prune.mjs'), '--check']],
  [process.execPath, ['--check', join(root, 'scripts', 'make-release-package.mjs')]],
]
for (const [command, args] of commands) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' })
  assert.equal(result.status, 0, `release check failed: ${command} ${args.join(' ')}`)
}

// 6) 品牌：控制台与 Hub 使用智造云 AIOS 标识；品牌资产在 branding/
assert.ok(existsSync(join(root, 'branding', 'gear-logo.png')), 'branding/gear-logo.png missing')
assert.ok(existsSync(join(root, 'branding', 'app.ico')), 'branding/app.ico missing')
const patch = readFileSync(join(scripts, 'patch-console-ui.mjs'), 'utf8')
assert.ok(patch.includes('智造云 AIOS'), 'patch-console-ui must brand as 智造云 AIOS')

console.log('智造云 AIOS 2.2.0 发布门禁通过：QwenPaw 2.2.0 唯一运行时、原生登录、跨平台入口（单机 8088 + Hub 8000）、控制台品牌化均正常。')
