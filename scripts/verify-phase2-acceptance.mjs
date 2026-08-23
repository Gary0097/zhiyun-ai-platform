import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const embedded = join(root, 'apps', 'qwenpaw-embedded')
const lock = JSON.parse(readFileSync(join(embedded, 'pawapps.lock.json'), 'utf8'))
const catalog = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'app_catalog.json'), 'utf8'))
const progress = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'feature_progress.json'), 'utf8'))

const hub = lock.apps.find(app => app.id === 'zhiyun-integration-hub')
assert.equal(hub?.commit, 'a3d90c2dba77e1d85f5c089957152bc7688e5707', 'Integration Hub must use formal PR #4 merge SHA')
assert.equal(catalog.apps.find(app => app.app_id === hub.id)?.version, '0.1.1')
assert.equal(JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-data-core', 'plugin.json'), 'utf8')).version, '0.7.0')
assert.equal(JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-audit', 'plugin.json'), 'utf8')).version, '1.3.0')

for (const file of [
  'plugins/zhiyun-data-core/operations.py',
  'plugins/zhiyun-data-core/test_operations.py',
  'apps/qwenpaw-embedded/scripts/verify-pawapp-offline.mjs',
  'docs/operations/PHASE-2-ACCEPTANCE.md',
]) assert.ok(existsSync(join(root, file)), `Phase 2 evidence missing: ${file}`)

for (const id of [29, 31]) {
  const feature = progress.features.find(item => item.id === id)
  assert.equal(feature?.status, 'testing', `feature ${id} must remain testing before live acceptance`)
  assert.ok(feature.progress < 100, `feature ${id} cannot be 100 before live acceptance`)
  assert.match(feature.note, /待用户实机验收/, `feature ${id} needs explicit acceptance boundary`)
}

const hubRoot = join(embedded, 'runtime', 'pawapps', 'zhiyun-integration-hub')
assert.equal(readFileSync(join(hubRoot, '.pawapp-commit'), 'utf8').trim(), hub.commit)
assert.ok(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('确认写入 Data Core'))
assert.ok(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('Q.registerRoutes("zhiyun-integration-hub"'))
assert.equal(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('document.getElementById("app")'), false)
console.log('Phase 2 候选检查通过：正式 Integration Hub SHA、Data Core、安全、离线恢复证据及待用户验收边界一致。')
