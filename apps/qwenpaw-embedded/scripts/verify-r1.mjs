import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const app = join(root, 'pawapps/zhiyun-orders')
const manifest = JSON.parse(readFileSync(join(app, 'plugin.json'), 'utf8'))
assert.equal(manifest.type, 'app')
assert.equal(manifest.meta.pawapp.entry_page, '/apps/zhiyun-orders')
assert.deepEqual(manifest.meta.tools.map(x => x.name), ['orders_query', 'orders_delivery_risk'])
const backend = readFileSync(join(app, 'backend/main.py'), 'utf8')
for (const contract of ['current_workspace()', 'data_origin', 'traceId', 'orders_delivery_risk']) assert.ok(backend.includes(contract), `missing backend contract: ${contract}`)
const ui = readFileSync(join(app, 'ui/index.js'), 'utf8')
for (const contract of ['Q.registerRoutes', '/apps/zhiyun-orders', 'Trace ID', '/zhiyun-orders/orders']) assert.ok(ui.includes(contract), `missing UI contract: ${contract}`)
const test = spawnSync(process.env.PYTHON || 'python', ['test_store.py'], { cwd: join(app, 'tests'), encoding: 'utf8' })
if (test.stdout) process.stdout.write(test.stdout)
if (test.stderr) process.stderr.write(test.stderr)
assert.equal(test.status, 0, 'orders Workspace store test failed')
const legacyRoutes = readFileSync(join(root, 'apps/enterprise/server/routes.js'), 'utf8')
assert.ok(!legacyRoutes.includes('/api/integrations/qwenpaw/tools/read'), 'legacy HTTP Tool Gateway route must be removed')
const start = readFileSync(join(root, 'apps/qwenpaw-enterprise/scripts/start-dev.mjs'), 'utf8')
assert.ok(!start.includes("['start.mjs']"), 'startup must not launch the external enterprise service')
assert.ok(start.includes("['plugin', 'install', orders"), 'startup must install the orders PawApp')
console.log('AI-OS Phase R1 verification passed: orders PawApp, Workspace SQLite, desktop UI, Agent tools and Trace')
