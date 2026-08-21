import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { dirname, isAbsolute, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const lockPath = join(appRoot, 'pawapps.lock.json')
const appsRoot = join(appRoot, 'runtime', 'pawapps')
const checkOnly = process.argv.includes('--check')

function fail (message) {
  console.error(`PawApp 同步失败：${message}`)
  process.exit(1)
}

function git (args, cwd, capture = false) {
  return spawnSync('git', args, {
    cwd,
    encoding: capture ? 'utf8' : undefined,
    stdio: capture ? 'pipe' : 'inherit'
  })
}

function validate (lock) {
  if (lock?.schema_version !== 1 || !Array.isArray(lock.apps)) fail('pawapps.lock.json 格式无效。')
  const ids = new Set()
  for (const app of lock.apps) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(app.id || '')) fail(`应用 ID 无效：${app.id || '(空)'}`)
    if (ids.has(app.id)) fail(`应用 ID 重复：${app.id}`)
    ids.add(app.id)
    if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\.git$/.test(app.repository || '')) fail(`${app.id} 仓库地址无效。`)
    if (!/^[0-9a-f]{40}$/.test(app.commit || '')) fail(`${app.id} 必须锁定 40 位提交 SHA。`)
    if (!app.install_dir || isAbsolute(app.install_dir) || app.install_dir.includes('/') || app.install_dir.includes('\\') || app.install_dir === '..') fail(`${app.id} 安装目录无效。`)
  }
}

function currentCommit (target) {
  if (!existsSync(join(target, '.git'))) return ''
  const result = git(['rev-parse', 'HEAD'], target, true)
  return result.status === 0 ? result.stdout.trim() : ''
}

function isMaterialized (target, app) {
  return currentCommit(target) === app.commit && existsSync(join(target, 'plugin.json'))
}

const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
validate(lock)
if (checkOnly) {
  console.log(`PawApp 锁文件检查通过：${lock.apps.length} 个应用。`)
  process.exit(0)
}

mkdirSync(appsRoot, { recursive: true })

for (const app of lock.apps) {
  const target = join(appsRoot, app.install_dir)
  if (isMaterialized(target, app)) {
    console.log(`PawApp 已就绪：${app.id} @ ${app.commit.slice(0, 8)}`)
  } else if (!existsSync(target)) {
    const clone = git(['clone', '--filter=blob:none', '--no-checkout', app.repository, target], appRoot)
    if (clone.status !== 0) fail(`无法克隆 ${app.id}；请检查网络或 GitHub 访问权限。`)
  } else if (!existsSync(join(target, '.git'))) {
    fail(`${target} 已存在但不是 Git 仓库，请移走后重试。`)
  }

  if (currentCommit(target) !== app.commit) {
    const fetch = git(['fetch', '--depth=1', 'origin', app.commit], target)
    if (fetch.status !== 0) fail(`无法获取 ${app.id} 的锁定版本，且本地没有该版本。`)
  }
  if (!isMaterialized(target, app)) {
    const checkout = git(['checkout', '--detach', '--force', app.commit], target)
    if (checkout.status !== 0) fail(`无法切换 ${app.id} 到锁定版本。`)
  }

  if (!isMaterialized(target, app)) fail(`${app.id} 提交或工作区文件校验失败。`)
  const manifestPath = join(target, 'plugin.json')
  if (!existsSync(manifestPath)) fail(`${app.id} 缺少 plugin.json。`)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  if (manifest.id !== app.id) fail(`${app.id} 的 plugin.json ID 不匹配。`)
  console.log(`PawApp 同步完成：${app.id} @ ${app.commit.slice(0, 8)}`)
}
