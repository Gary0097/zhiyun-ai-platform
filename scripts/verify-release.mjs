// 智造云 AIOS 2.2.1 发布门禁（极简形态：无捆绑业务应用）
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

// 1) 版本锁一致性（唯一运行时 = QwenPaw 2.2.1）
const qwenpawLock = JSON.parse(readFileSync(join(embedded, 'qwenpaw.lock.json'), 'utf8'))
assert.equal(qwenpawLock.version, '2.2.1')
assert.equal(qwenpawLock.ref, 'v2.2.1')
const installerManifest = readFileSync(join(root, 'scripts/exe-installer/installer.manifest'), 'utf8')
assert.equal(installerManifest.match(/<assemblyIdentity\s+version="([^"]+)"/)?.[1], qwenpawLock.version + '.0', 'installer manifest must match runtime lock')
assert.ok(!existsSync(join(embedded, 'pawapps.lock.json')), '2.2.1 极简形态不应存在 PawApp 锁')

// 2) 跨平台入口完整性（单机 8088 + Hub 8000）
for (const entry of [
  'setup-ai-os.ps1', 'setup-ai-os.sh', 'setup-hub.ps1', 'setup-hub.sh',
  'start-ai-os.cmd', 'start-ai-os.sh', 'start-hub.cmd', 'start-hub.sh', 'start-hub.ps1',
  'diagnose-ai-os.cmd', 'diagnose-ai-os.sh', 'install-oneclick.cmd', 'install-oneclick.sh',
  'update-ai-os.cmd', 'update-ai-os.ps1', 'update-ai-os.sh',
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
  [process.execPath, ['--test', join(root, 'scripts', 'updates', 'test-updates.mjs')]],
  [process.execPath, [join(root, 'scripts', 'test-workspace-paths.mjs')]],
  [process.execPath, [join(root, 'scripts', 'test-hub-config.mjs')]],
  [process.env.PYTHON || 'python', [join(root, 'scripts', 'test-hub-bootstrap.py')]],
  [process.execPath, ['--check', join(scripts, 'start.mjs')]],
  [process.execPath, ['--check', join(scripts, 'runtime-env.mjs')]],
  [process.execPath, ['--check', join(scripts, 'doctor.mjs')]],
  [process.execPath, ['--check', join(scripts, 'ensure-workspace.mjs')]],
  [process.execPath, ['--check', join(scripts, 'patch-console-ui.mjs')]],
  [process.execPath, ['--check', join(scripts, 'provision-office-skills.mjs')]],
  [process.execPath, [join(scripts, 'provision-office-skills.mjs'), '--check']],
  [process.execPath, [join(scripts, 'test-provision-office-skills.mjs')]],
  [process.execPath, ['--check', join(scripts, 'ensure-office-deps.mjs')]],
  [process.execPath, [join(scripts, 'ensure-office-deps.mjs'), '--check']],
  [process.execPath, [join(scripts, 'test-ensure-office-deps.mjs')]],
  [process.execPath, ['--check', join(scripts, 'link-zcode-skills.mjs')]],
  [process.execPath, ['--check', join(scripts, 'check-office-pack.mjs')]],
  [process.execPath, [join(scripts, 'link-zcode-skills.mjs'), '--check']],
  [process.execPath, [join(scripts, 'test-link-zcode-skills.mjs')]],
  [process.execPath, [join(scripts, 'verify-runtime.mjs')]],
  [process.execPath, [join(scripts, 'patch-console-ui.mjs'), '--check']],
  [process.execPath, [join(scripts, 'test-patch-console-ui.mjs')]],
  [process.execPath, [join(root, 'scripts', 'release-prune.mjs'), '--check']],
  [process.execPath, ['--check', join(root, 'scripts', 'make-release-package.mjs')]],
]
if (process.platform === 'win32') commands.push(['powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', join(root, 'scripts', 'updates', 'test-recovery.ps1')]])
if (process.platform === 'win32') commands.push(['powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', join(root, 'scripts', 'test-installer.ps1')]])
if (process.platform === 'win32') commands.push(['powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', join(root, 'scripts', 'test-windows-runtime-paths.ps1')]])
for (const [command, args] of commands) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' })
  assert.equal(result.status, 0, `release check failed: ${command} ${args.join(' ')}`)
}

// 6) 品牌：控制台与 Hub 使用智造云 AIOS 标识；品牌资产在 branding/
assert.ok(existsSync(join(root, 'branding', 'gear-logo.png')), 'branding/gear-logo.png missing')
assert.ok(existsSync(join(root, 'branding', 'app.ico')), 'branding/app.ico missing')
const patch = readFileSync(join(scripts, 'patch-console-ui.mjs'), 'utf8')
assert.ok(patch.includes('智造云AIOS'), 'patch-console-ui must brand as 智造云 AIOS')

// 7) 办公专属默认技能包（aios-office 分支）：清单、11 项技能 frontmatter、
//    预装依赖清单、预置脚本挂接单机与 Hub 启动链路、测试纳入门禁
const officePackRoot = join(root, 'skills', 'office')
const officePackPath = join(officePackRoot, 'office-pack.json')
assert.ok(existsSync(officePackPath), 'skills/office/office-pack.json missing')
const officePack = JSON.parse(readFileSync(officePackPath, 'utf8'))
assert.ok(Array.isArray(officePack.skills) && officePack.skills.length === 11, 'office pack must declare 11 skills')
for (const dir of officePack.skills) {
  assert.ok(existsSync(join(officePackRoot, dir, 'SKILL.md')), `office skill missing: skills/office/${dir}/SKILL.md`)
}
const officeRequirements = join(officePackRoot, 'requirements-office.txt')
assert.ok(existsSync(officeRequirements), 'skills/office/requirements-office.txt missing')
assert.ok(readFileSync(officeRequirements, 'utf8').includes('rapidocr-onnxruntime'), 'office deps must include the local OCR fallback')
assert.ok(existsSync(join(scripts, 'provision-office-skills.mjs')), 'provision-office-skills.mjs missing')
assert.ok(existsSync(join(scripts, 'ensure-office-deps.mjs')), 'ensure-office-deps.mjs missing')
assert.ok(existsSync(join(scripts, 'link-zcode-skills.mjs')), 'link-zcode-skills.mjs missing (ZCode office skills bridge)')
const ensureWorkspaceSrc = readFileSync(join(scripts, 'ensure-workspace.mjs'), 'utf8')
assert.ok(ensureWorkspaceSrc.includes('provision-office-skills'), 'ensure-workspace.mjs must provision the office skill pack')
assert.ok(ensureWorkspaceSrc.includes('ensure-office-deps'), 'ensure-workspace.mjs must preinstall the office dependencies')
assert.ok(ensureWorkspaceSrc.includes('link-zcode-skills'), 'ensure-workspace.mjs must hook the ZCode skills bridge')
for (const hubEntry of ['start-hub.ps1', 'start-hub.sh']) {
  assert.ok(readFileSync(join(root, hubEntry), 'utf8').includes('provision-office-skills'), `${hubEntry} must provision the office skill pack`)
}

// 7.5) 办公模式质量项（#aios-office v1.2.0）：
//   - token 预算：preload=false 时 description 是每轮固定注入，必须保持精简；
//   - 文件下载修复与启动快跳必须存在于品牌补丁；
//   - 品牌插件安装必须版本门控（启动提速）。
for (const dir of officePack.skills) {
  const skillMd = readFileSync(join(officePackRoot, dir, 'SKILL.md'), 'utf8')
  const desc = skillMd.match(/^description: "(.*)"$/m)?.[1] || ''
  assert.ok(desc.length > 0 && desc.length <= 110,
    `office skill ${dir} description 长度必须在 1-110 字符（当前 ${desc.length}）：description 是每轮对话的固定 token 开销`)
}
const patchSrc = readFileSync(join(scripts, 'patch-console-ui.mjs'), 'utf8')
assert.ok(patchSrc.includes('%2525'), 'patch-console-ui must carry the file-preview URL encoding fix (#/? 截断与 % 双重解码 404)')
assert.ok(patchSrc.includes('.aios-console-patch.sig'), 'patch-console-ui must implement the content-signature fast skip (启动提速)')
const startSrc = readFileSync(join(scripts, 'start.mjs'), 'utf8')
assert.ok(startSrc.includes('.brand-plugin.version'), 'start.mjs must version-gate the brand plugin install (启动提速)')
const provisionerSrc = readFileSync(join(scripts, 'provision-office-skills.mjs'), 'utf8')
assert.ok(provisionerSrc.includes('OFFICE.md') && provisionerSrc.includes('system_prompt_files'),
  'provisioner must provision the compact OFFICE.md reply discipline and slim the default system_prompt_files')
assert.ok(existsSync(join(scripts, 'check-office-pack.mjs')), 'check-office-pack.mjs missing (办公版体检)')
for (const entry of ['check-ai-os.cmd', 'check-ai-os.sh']) {
  assert.ok(readFileSync(join(root, entry), 'utf8').includes('check-office-pack'), `${entry} must run the office pack health check`)
}

console.log('智造云 AIOS 2.2.1 发布门禁通过：QwenPaw 2.2.1 唯一运行时、原生登录、跨平台入口（单机 8088 + Hub 8000）、控制台品牌化、办公完全体（11 项默认启用 + 依赖预装 + ZCode 桥接 + token 预算 + 文件下载修复 + 启动提速）均正常。')
