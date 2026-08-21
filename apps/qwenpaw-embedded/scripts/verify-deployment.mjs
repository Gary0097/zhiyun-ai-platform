import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const scripts = join(root, 'apps', 'qwenpaw-embedded', 'scripts')

for (const file of ['start-ai-os.cmd', 'start-ai-os.sh', 'diagnose-ai-os.cmd', 'diagnose-ai-os.sh', 'docs/operations/QUICKSTART.md']) {
  assert.ok(existsSync(join(root, file)), `missing deployment file: ${file}`)
}

const start = readFileSync(join(scripts, 'start.mjs'), 'utf8')
assert.ok(start.includes("join(scriptsRoot, 'doctor.mjs')"), 'start must run doctor before installation')
assert.ok(start.indexOf('doctor.mjs') < start.indexOf('cleanup-legacy.py'), 'doctor must run before mutations')

const result = spawnSync(process.execPath, [join(scripts, 'doctor.mjs'), '--json'], { cwd: root, encoding: 'utf8' })
const report = JSON.parse(result.stdout)
assert.equal(typeof report.ok, 'boolean')
for (const id of ['node', 'git', 'qwenpaw-cli', 'python-runtime', 'directories', 'pawapps-lock', 'pawapps', 'port-8088']) {
  assert.ok(report.checks.some(check => check.id === id), `doctor missing check: ${id}`)
}
assert.ok([0, 1].includes(result.status), 'doctor must exit deterministically')

console.log('部署回归通过：跨平台入口、预启动诊断、PawApp 与端口检查均存在。')
