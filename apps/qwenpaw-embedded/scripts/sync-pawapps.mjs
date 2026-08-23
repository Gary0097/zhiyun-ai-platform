import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = process.env.AI_OS_EMBEDDED_ROOT
  ? resolve(process.env.AI_OS_EMBEDDED_ROOT)
  : join(dirname(fileURLToPath(import.meta.url)), '..')
const lockPath = join(appRoot, 'pawapps.lock.json')
const appsRoot = join(appRoot, 'runtime', 'pawapps')
const cacheRoot = join(appRoot, 'runtime', 'cache', 'pawapps')
const checkOnly = process.argv.includes('--check')
const offline = process.env.AI_OS_OFFLINE === '1' || process.env.UV_OFFLINE === '1'

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

function isMaterialized (target, app) {
  const marker = join(target, '.pawapp-commit')
  return existsSync(marker) && readFileSync(marker, 'utf8').trim() === app.commit && existsSync(join(target, 'plugin.json')) && !existsSync(join(target, '.git'))
}

const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
validate(lock)
if (checkOnly) {
  console.log(`PawApp 锁文件检查通过：${lock.apps.length} 个应用。`)
  process.exit(0)
}

mkdirSync(appsRoot, { recursive: true })
mkdirSync(cacheRoot, { recursive: true })

function bundlePath (app) {
  return join(cacheRoot, `${app.id}-${app.commit}.bundle`)
}

function cacheBundle (app) {
  const bundle = bundlePath(app)
  if (existsSync(bundle) || offline) return
  const cacheStage = join(appsRoot, `.${app.id}.cache-${process.pid}`)
  rmSync(cacheStage, { recursive: true, force: true })
  const clone = git(['clone', '--filter=blob:none', '--no-checkout', app.repository, cacheStage], appRoot)
  if (clone.status !== 0) { console.warn(`警告：暂时无法为 ${app.id} 创建离线缓存；现有安装仍可使用。`); rmSync(cacheStage, { recursive: true, force: true }); return }
  const fetch = git(['fetch', '--depth=1', 'origin', app.commit], cacheStage)
  if (fetch.status !== 0) { console.warn(`警告：暂时无法缓存 ${app.id} 的锁定版本。`); rmSync(cacheStage, { recursive: true, force: true }); return }
  const checkout = git(['checkout', '--detach', '--force', app.commit], cacheStage)
  if (checkout.status !== 0) { console.warn(`警告：暂时无法检出 ${app.id} 的缓存版本。`); rmSync(cacheStage, { recursive: true, force: true }); return }
  const bundled = git(['bundle', 'create', bundle, 'HEAD'], cacheStage)
  rmSync(cacheStage, { recursive: true, force: true })
  if (bundled.status !== 0 || !existsSync(bundle)) console.warn(`警告：暂时无法生成 ${app.id} 的离线 bundle。`)
}

for (const app of lock.apps) {
  const target = join(appsRoot, app.install_dir)
  if (isMaterialized(target, app)) {
    cacheBundle(app)
    console.log(`PawApp 已就绪：${app.id} @ ${app.commit.slice(0, 8)}`)
    continue
  }
  const staging = `${target}.sync-${process.pid}`
  rmSync(staging, { recursive: true, force: true })
  const bundle = bundlePath(app)
  const source = offline ? bundle : app.repository
  if (offline && !existsSync(bundle)) fail(`${app.id} 缺少离线 bundle：${bundle}`)
  const cloneArgs = offline ? ['clone', '--no-checkout', source, staging] : ['clone', '--filter=blob:none', '--no-checkout', source, staging]
  const clone = git(cloneArgs, appRoot)
  if (clone.status !== 0) fail(`无法克隆 ${app.id}；请检查网络或 GitHub 访问权限。`)
  if (!offline) {
    const fetch = git(['fetch', '--depth=1', 'origin', app.commit], staging)
    if (fetch.status !== 0) fail(`无法获取 ${app.id} 的锁定版本。`)
  }
  const checkout = git(['checkout', '--detach', '--force', app.commit], staging)
  if (checkout.status !== 0) fail(`无法切换 ${app.id} 到锁定版本。`)
  if (!offline && !existsSync(bundle)) {
    const bundled = git(['bundle', 'create', bundle, 'HEAD'], staging)
    if (bundled.status !== 0) fail(`无法生成 ${app.id} 的离线 bundle。`)
  }
  const manifestPath = join(staging, 'plugin.json')
  if (!existsSync(manifestPath)) fail(`${app.id} 缺少 plugin.json。`)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  if (manifest.id !== app.id) fail(`${app.id} 的 plugin.json ID 不匹配。`)
  rmSync(join(staging, '.git'), { recursive: true, force: true })
  writeFileSync(join(staging, '.pawapp-commit'), `${app.commit}\n`, 'utf8')
  rmSync(target, { recursive: true, force: true })
  renameSync(staging, target)
  if (!isMaterialized(target, app)) fail(`${app.id} 提交或工作区文件校验失败。`)
  console.log(`PawApp 同步完成：${app.id} @ ${app.commit.slice(0, 8)}`)
}
