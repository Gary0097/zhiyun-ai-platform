import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const scripts = join(root, 'apps', 'qwenpaw-embedded', 'scripts')

for (const file of ['setup-ai-os.ps1', 'setup-ai-os.sh', 'start-ai-os.cmd', 'start-ai-os.sh', 'diagnose-ai-os.cmd', 'diagnose-ai-os.sh', 'check-ai-os.cmd', 'check-ai-os.sh', 'docs/operations/QUICKSTART.md']) {
  assert.ok(existsSync(join(root, file)), `missing deployment file: ${file}`)
}

const windowsStart = readFileSync(join(root, 'start-ai-os.cmd'), 'utf8')
const linuxStart = readFileSync(join(root, 'start-ai-os.sh'), 'utf8')
assert.ok(windowsStart.includes('runtime\\qwenpaw\\venv\\Scripts\\qwenpaw.exe'), 'Windows wrapper must recognize the managed venv layout')
assert.ok(linuxStart.includes('runtime/qwenpaw/venv/bin/qwenpaw'), 'Linux wrapper must recognize the managed venv layout')

const start = readFileSync(join(scripts, 'start.mjs'), 'utf8')
assert.ok(start.includes("from './runtime-env.mjs'"), 'start must resolve the project-managed QwenPaw runtime')
assert.ok(start.includes('qwenpawCommand'), 'start must not require a global qwenpaw command')
assert.ok(start.includes("join(scriptsRoot, 'doctor.mjs')"), 'start must run doctor before installation')
assert.ok(start.indexOf('doctor.mjs') < start.indexOf('cleanup-legacy.mjs'), 'doctor must run before mutations')
assert.ok(start.includes('for (const app of externalApps)'), 'start must install every locked external PawApp')
assert.ok(start.includes("join(scriptsRoot, 'health-report.mjs')"), 'start must launch the post-start health report')

const sync = readFileSync(join(scripts, 'sync-pawapps.mjs'), 'utf8')
assert.ok(sync.includes("'.pawapp-commit'"), 'sync must persist a commit marker')
assert.ok(sync.includes("rmSync(join(staging, '.git')"), 'sync must remove Git metadata before plugin installation')
const doctor = readFileSync(join(scripts, 'doctor.mjs'), 'utf8')
assert.ok(doctor.includes("from './runtime-env.mjs'"), 'doctor must report the selected runtime source')
assert.ok(doctor.includes('setup-ai-os'), 'doctor must provide the project runtime repair command')
assert.ok(doctor.includes("portInUse ? 'fail' : 'pass'"), 'occupied 8088 must stop duplicate startup before mutation')

const health = readFileSync(join(scripts, 'health-report.mjs'), 'utf8')
for (const endpoint of ['zhiyun-logo', 'zhiyun-app-discovery', 'zhiyun-data-core', 'zhiyun-data-studio', 'zhiyun-order-studio']) {
  assert.ok(health.includes(endpoint), `health report missing endpoint: ${endpoint}`)
}
const healthCheck = spawnSync(process.execPath, [join(scripts, 'health-report.mjs'), '--check'], { cwd: root, encoding: 'utf8' })
assert.equal(healthCheck.status, 0, 'health report configuration must be valid')
assert.ok(health.includes('validatePayload') && health.includes('validateContracts'), 'health report must validate payload semantics and version contracts')

const result = spawnSync(process.execPath, [join(scripts, 'doctor.mjs'), '--json'], { cwd: root, encoding: 'utf8' })
const report = JSON.parse(result.stdout)
assert.equal(typeof report.ok, 'boolean')
for (const id of ['node', 'git', 'qwenpaw-cli', 'python-runtime', 'directories', 'pawapps-lock', 'pawapps', 'port-8088']) {
  assert.ok(report.checks.some(check => check.id === id), `doctor missing check: ${id}`)
}
assert.ok([0, 1].includes(result.status), 'doctor must exit deterministically')

console.log('部署回归通过：跨平台入口、预启动诊断、运行健康报告、PawApp 与端口检查均存在。')
