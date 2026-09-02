import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const embedded = join(root, 'apps', 'zhizaoyunAIOS')
const lock = JSON.parse(readFileSync(join(embedded, 'pawapps.lock.json'), 'utf8'))
const catalog = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'app_catalog.json'), 'utf8'))
const progress = JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-app-discovery', 'feature_progress.json'), 'utf8'))

const hub = lock.apps.find(app => app.id === 'zhiyun-integration-hub')
assert.equal(hub?.commit, 'be45c71103a593697f5a5d9bd360b0718f825997', 'Integration Hub must use formal PR #6 merge SHA')
assert.equal(catalog.apps.find(app => app.app_id === hub.id)?.version, '0.2.2')
assert.equal(JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-data-core', 'plugin.json'), 'utf8')).version, '0.8.0')
assert.equal(JSON.parse(readFileSync(join(root, 'plugins', 'zhiyun-audit', 'plugin.json'), 'utf8')).version, '1.3.0')

for (const file of [
  'plugins/zhiyun-data-core/operations.py',
  'plugins/zhiyun-data-core/test_operations.py',
  'apps/zhizaoyunAIOS/scripts/verify-pawapp-offline.mjs',
  'docs/operations/PHASE-2-ACCEPTANCE.md',
]) assert.ok(existsSync(join(root, file)), `Phase 2 evidence missing: ${file}`)

for (const id of [29, 31]) {
  const feature = progress.features.find(item => item.id === id)
  assert.equal(feature?.status, 'completed', `feature ${id} must record live acceptance`)
  assert.equal(feature.progress, 100, `feature ${id} must be 100 after live acceptance`)
  assert.match(feature.note, /2026-08-23.*用户实机验收/, `feature ${id} needs dated live acceptance evidence`)
}

const hubRoot = join(embedded, 'runtime', 'pawapps', 'zhiyun-integration-hub')
assert.equal(readFileSync(join(hubRoot, '.pawapp-commit'), 'utf8').trim(), hub.commit)
assert.ok(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('确认写入统一数据中心'))
assert.equal(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('配置 JSON'), false)
assert.equal(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('字段映射 JSON'), false)
assert.ok(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('Q.registerRoutes("zhiyun-integration-hub"'))
assert.equal(readFileSync(join(hubRoot, 'ui', 'index.js'), 'utf8').includes('document.getElementById("app")'), false)
console.log('Phase 2 验收检查通过：正式 Integration Hub SHA、Data Core、安全、离线恢复证据及用户实机验收记录一致。')
