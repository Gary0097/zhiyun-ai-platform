// 智造云 AIOS 2.2.0 发布门禁（极简形态：无捆绑业务应用）
// 检查：跨平台入口完整性、版本锁一致性、脚本语法、控制台品牌化、
// 打包/清理脚本自检。业务应用已剥离，其验收由各应用独立仓库自行承担。
import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
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
// #126 后允许安装系统品牌层插件 aios-brand；业务插件安装仍禁止
const brandMarker = "const brandPlugin = join(repoRoot, 'plugins', 'aios-brand')"
const [beforeBrand, afterBrand] = start.split(brandMarker)
const brandBlockEnd = afterBrand ? afterBrand.indexOf('\n}') : -1
const startOutsideBrand = beforeBrand + (afterBrand ? afterBrand.slice(brandBlockEnd + 2) : '')
assert.ok(!startOutsideBrand.includes('plugin'), 'start.mjs must not install business plugins (aios-brand is the sanctioned system brand plugin)')

// 4) 业务应用剥离后不得残留脚本引用
for (const banned of ['sync-pawapps', 'pawapp-materialized', 'seed-builtin-agents', 'health-report', 'set-logo', 'cleanup-legacy']) {
  assert.ok(!existsSync(join(scripts, banned + '.mjs')), `leftover business script: ${banned}.mjs`)
}
// #126：仓库内只允许品牌层插件 aios-brand（官方扩展点形态）；其余业务插件仍禁止
if (existsSync(join(root, 'plugins'))) {
  const allowed = new Set(['aios-brand'])
  for (const entry of readdirSync(join(root, 'plugins'))) {
    assert.ok(allowed.has(entry), `unexpected vendored plugin: plugins/${entry}`)
  }
  const manifest = JSON.parse(readFileSync(join(root, 'plugins', 'aios-brand', 'plugin.json'), 'utf8'))
  assert.equal(manifest.id, 'aios-brand', 'brand plugin manifest id mismatch')
  assert.ok(manifest.type === 'frontend' && existsSync(join(root, 'plugins', 'aios-brand', manifest.entry.frontend)), 'brand plugin frontend entry missing')
}

// 4.5) 控制台存在性：本机已有项目运行时却找不到 console 属于异常（品牌检查
// 会静默跳过、门禁虚绿）；完全干净的检出（CI）无运行时，需显式放行环境变量。
const runtimeRoot = join(root, 'apps', 'zhizaoyunAIOS', 'runtime', 'zhizaoyunAIOS')
const runtimeExists = existsSync(runtimeRoot)
const allowNoConsole = process.env.GITHUB_ACTIONS === 'true' || process.env.ZY_ALLOW_NO_CONSOLE === '1'
if (runtimeExists) {
  const hasConsole = ['venv/Lib/site-packages/qwenpaw/console/index.html', 'venv/lib/python3.12/site-packages/qwenpaw/console/index.html']
    .some(rel => existsSync(join(runtimeRoot, ...rel.split('/'))))
  assert.ok(hasConsole, 'project runtime exists but qwenpaw console is missing (branding checks would silently skip)')
} else if (!allowNoConsole) {
  console.error('警告：未找到项目运行时，控制台品牌检查将跳过。确需跳过请设置 ZY_ALLOW_NO_CONSOLE=1。')
  process.exit(1)
}

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
assert.ok(patch.includes('智造云AIOS'), 'patch-console-ui must brand as 智造云 AIOS')

console.log('智造云 AIOS 2.2.0 发布门禁通过：QwenPaw 2.2.0 唯一运行时、原生登录、跨平台入口（单机 8088 + Hub 8000）、控制台品牌化均正常。')
