import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const lock = JSON.parse(readFileSync(join(root, 'apps/qwenpaw-embedded/qwenpaw.lock.json'), 'utf8'))
assert.equal(lock.commit, 'e4995dcf516d27400fbc33891aa3dcbcf79acc7a')
assert.equal(lock.integration, 'embedded-downstream')
for (const dir of ['data', 'logs', 'files', 'knowledge', 'artifacts']) {
  assert.ok(existsSync(join(root, 'apps/qwenpaw-embedded/workspace/template', dir, '.gitkeep')), `missing workspace directory: ${dir}`)
}
const prd = readFileSync(join(root, 'docs/product/AI-OS-PRD-V5.0-Embedded-QwenPaw.md'), 'utf8')
for (const contract of ['data/ai-os.sqlite', 'logs/runtime.jsonl', 'PawApp', 'ctx.ui.confirm', 'HTTP Enterprise Gateway']) assert.ok(prd.includes(contract), `missing PRD contract: ${contract}`)
const appSpec = readFileSync(join(root, 'pawapps/README.md'), 'utf8')
assert.ok(appSpec.includes('plugin.json.meta.tools'))
assert.ok(appSpec.includes('禁止使用进程当前目录'))
const workspaceTest = spawnSync(process.env.PYTHON || 'python', ['test_workspace.py'], {
  cwd: join(root, 'pawapps/_shared'), encoding: 'utf8'
})
if (workspaceTest.stdout) process.stdout.write(workspaceTest.stdout)
if (workspaceTest.stderr) process.stderr.write(workspaceTest.stderr)
assert.equal(workspaceTest.status, 0, 'Workspace SQLite/JSONL core test failed')
console.log('AI-OS Phase R0 verification passed: embedded QwenPaw, Workspace data/logs, PawApp package contract')
