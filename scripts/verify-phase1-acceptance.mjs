import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const embedded = join(root, 'apps', 'qwenpaw-embedded')
const installed = join(embedded, 'runtime', 'pawapps')
const lock = JSON.parse(readFileSync(join(embedded, 'pawapps.lock.json'), 'utf8'))
const progress = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'feature_progress.json'), 'utf8'))
const catalog = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'app_catalog.json'), 'utf8'))

const expected = {
  'zhiyun-data-studio': {
    commit: 'd5734d1be6b288a170b6a2916dcd63d2bdebe9be', version: '0.9.2',
    files: ['backend/insight_workflow.py', 'tests/test_insight_workflow.py'],
    source: ['@router.post("/artifacts")', 'tool_name="analyze_order_delivery_risk"'],
  },
  'zhiyun-order-studio': {
    commit: '9edd776ab9c7038fc00f34b61509cd3466bddd76', version: '0.7.2',
    files: ['backend/exception_engine.py', 'tests/test_exception_workflow.py'],
    source: ['@router.post("/exceptions")', 'tool_name="run_order_exception_workflow"'],
  },
}

for (const [id, contract] of Object.entries(expected)) {
  const locked = lock.apps.find(app => app.id === id)
  const entry = catalog.apps.find(app => app.app_id === id)
  const appRoot = join(installed, id)
  assert.equal(locked?.commit, contract.commit, `${id} must use the formal Phase 1 merge SHA`)
  assert.equal(entry?.version, contract.version, `${id} catalog version drift`)
  assert.equal(JSON.parse(readFileSync(join(appRoot, 'plugin.json'), 'utf8')).version, contract.version)
  for (const file of contract.files) assert.ok(existsSync(join(appRoot, file)), `${id} missing ${file}`)
  const main = readFileSync(join(appRoot, 'backend', 'main.py'), 'utf8')
  for (const marker of contract.source) assert.ok(main.includes(marker), `${id} missing ${marker}`)
}

const phase1 = progress.features.filter(feature => feature.id >= 1 && feature.id <= 11)
assert.equal(phase1.length, 11)
for (const feature of phase1) {
  assert.equal(feature.status, 'completed', `feature ${feature.id} must record completed user acceptance`)
  assert.equal(feature.progress, 100, `feature ${feature.id} must be 100 after user acceptance`)
  assert.match(feature.note, /2026-08-23.*用户实机验收/, `feature ${feature.id} needs dated user-acceptance evidence`)
}

console.log('Phase 1 验收检查通过：正式合并 SHA、版本、功能 1–11 实现证据及用户实机验收记录一致。')
