import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

const root = mkdtempSync(join(tmpdir(), 'zhiyun-offline-'))
const source = join(root, 'source')
const embedded = join(root, 'embedded')
const script = join(embedded, 'scripts', 'sync-pawapps.mjs')

function git (args, cwd) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8' })
  assert.equal(result.status, 0, result.stderr || result.stdout)
  return result.stdout.trim()
}

try {
  mkdirSync(source)
  git(['init'], source)
  git(['config', 'user.name', 'Phase 2 Test'], source)
  git(['config', 'user.email', 'phase2@example.invalid'], source)
  writeFileSync(join(source, 'plugin.json'), JSON.stringify({ id: 'offline-test-app', version: '1.0.0' }))
  git(['add', 'plugin.json'], source)
  git(['commit', '-m', 'fixture'], source)
  const commit = git(['rev-parse', 'HEAD'], source)
  mkdirSync(join(embedded, 'scripts'), { recursive: true })
  mkdirSync(join(embedded, 'runtime', 'cache', 'pawapps'), { recursive: true })
  cpSync(new URL('./sync-pawapps.mjs', import.meta.url), script)
  const bundle = join(embedded, 'runtime', 'cache', 'pawapps', `offline-test-app-${commit}.bundle`)
  git(['bundle', 'create', bundle, 'HEAD'], source)
  writeFileSync(join(embedded, 'pawapps.lock.json'), JSON.stringify({ schema_version: 1, apps: [{
    id: 'offline-test-app', repository: 'https://github.com/example/offline-test-app.git',
    ref: 'main', commit, install_dir: 'offline-test-app',
  }] }))
  const result = spawnSync(process.execPath, [script], {
    env: { ...process.env, AI_OS_EMBEDDED_ROOT: embedded, AI_OS_OFFLINE: '1' }, encoding: 'utf8',
  })
  assert.equal(result.status, 0, result.stderr || result.stdout)
  const installed = join(embedded, 'runtime', 'pawapps', 'offline-test-app')
  assert.equal(readFileSync(join(installed, '.pawapp-commit'), 'utf8').trim(), commit)
  assert.equal(existsSync(join(installed, '.git')), false)
  console.log('PawApp 离线恢复回归通过：锁定 bundle 可在无网络路径下重建安装。')
} finally {
  rmSync(root, { recursive: true, force: true })
}
