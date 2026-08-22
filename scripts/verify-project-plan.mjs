import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const progressPath = join(root, 'plugins', 'zhiyun-app-discovery', 'feature_progress.json')
const lockPath = join(root, 'apps', 'qwenpaw-embedded', 'pawapps.lock.json')
const catalogPath = join(root, 'plugins', 'zhiyun-app-discovery', 'app_catalog.json')

const progress = JSON.parse(readFileSync(progressPath, 'utf8'))
const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
const catalog = JSON.parse(readFileSync(catalogPath, 'utf8'))

assert.equal(progress.schema_version, 1, 'unsupported feature progress schema')
assert.match(progress.updated_at, /^\d{4}-\d{2}-\d{2}$/, 'feature progress requires an ISO date')
assert.ok(Array.isArray(progress.features) && progress.features.length > 0, 'feature progress must not be empty')

const allowedStatuses = new Set(['planned', 'in_progress', 'testing', 'completed'])
const featureIds = new Set()
for (const feature of progress.features) {
  assert.ok(Number.isInteger(feature.id) && feature.id > 0, 'feature IDs must be positive integers')
  assert.equal(featureIds.has(feature.id), false, `duplicate feature ID: ${feature.id}`)
  featureIds.add(feature.id)
  assert.equal(typeof feature.name, 'string', `feature ${feature.id} requires a name`)
  assert.ok(feature.name.trim(), `feature ${feature.id} requires a non-empty name`)
  assert.match(feature.app_id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/, `feature ${feature.id} has an invalid app_id`)
  assert.ok(allowedStatuses.has(feature.status), `feature ${feature.id} has invalid status: ${feature.status}`)
  assert.ok(Number.isInteger(feature.progress) && feature.progress >= 0 && feature.progress <= 100, `feature ${feature.id} progress must be an integer from 0 to 100`)
  assert.equal(typeof feature.note, 'string', `feature ${feature.id} requires an evidence note`)
  assert.ok(feature.note.trim(), `feature ${feature.id} requires a non-empty evidence note`)

  if (feature.status === 'planned') assert.equal(feature.progress, 0, `planned feature ${feature.id} must remain at 0%`)
  if (feature.status === 'completed') assert.equal(feature.progress, 100, `completed feature ${feature.id} must be at 100%`)
  if (feature.progress === 100) assert.equal(feature.status, 'completed', `feature ${feature.id} at 100% must be completed`)
}

const lockedAppIds = new Set(lock.apps.map(app => app.id))
for (const required of ['zhiyun-data-studio', 'zhiyun-order-studio']) {
  assert.ok(lockedAppIds.has(required), `${required} must remain in the external PawApp lock`)
}

const catalogAppIds = new Set(catalog.apps.map(app => app.app_id))
for (const appId of lockedAppIds) {
  assert.ok(catalogAppIds.has(appId), `locked PawApp ${appId} must exist in the application catalog`)
}

const counts = Object.fromEntries([...allowedStatuses].map(status => [
  status,
  progress.features.filter(feature => feature.status === status).length,
]))
const complete = counts.completed === progress.features.length

console.log(`项目计划检查通过：${progress.features.length} 项能力；已完成 ${counts.completed}，测试中 ${counts.testing}，开发中 ${counts.in_progress}，计划中 ${counts.planned}。`)
if (!complete) console.log('项目仍在开发中；不得将当前进度描述为“全部完成”。')
