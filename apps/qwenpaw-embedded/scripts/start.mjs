import { spawn, spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime, runtimeEnvironment } from './runtime-env.mjs'

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const scriptsRoot = join(appRoot, 'scripts')
const auditPlugin = join(repoRoot, 'plugins', 'zhiyun-audit')
const logoPlugin = join(repoRoot, 'plugins', 'zhiyun-logo')
const appDiscoveryPlugin = join(repoRoot, 'plugins', 'zhiyun-app-discovery')
const dataCorePlugin = join(repoRoot, 'plugins', 'zhiyun-data-core')
const pawappsLock = join(appRoot, 'pawapps.lock.json')
const runtime = resolveRuntime()
const launchEnv = runtimeEnvironment(runtime)
const qwenpawCommand = runtime.command || 'qwenpaw'

// Point every Studio backend at a writable, shared runtime data directory so
// module runs never fall back to a read-only per-user path.
const runtimeData = join(repoRoot, '..', '.qwenpaw-runtime-data')
Object.assign(launchEnv, {
  QWENPAW_WORKING_DIR: join(appRoot, 'workspace'),
  SERVICE_STUDIO_DB: join(runtimeData, 'zhiyun-service-studio', 'service.db'),
  SUPPLY_STUDIO_DB: join(runtimeData, 'zhiyun-supply-studio', 'supply.db'),
  SALES_STUDIO_DB: join(runtimeData, 'zhiyun-sales-studio', 'sales.db'),
  FINANCE_STUDIO_DB: join(runtimeData, 'zhiyun-finance-studio', 'finance.db'),
  PEOPLE_STUDIO_DB: join(runtimeData, 'zhiyun-people-studio', 'people.db'),
  DATA_STUDIO_DB: join(runtimeData, 'zhiyun-data-studio', 'insights.db'),
  ORDER_STUDIO_DB: join(runtimeData, 'zhiyun-order-studio', 'orders.db')
})

function run (command, args, hint, capture = false) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: capture ? 'utf8' : undefined,
    stdio: capture ? 'pipe' : 'inherit',
    env: launchEnv
  })
  if (result.error || result.status !== 0) {
    console.error(`\n${hint}`)
    if (capture && result.stderr) console.error(result.stderr.trim())
    process.exit(result.status || 1)
  }
  return capture ? `${result.stdout || ''}${result.stderr || ''}`.trim() : ''
}

run(process.execPath, [join(scriptsRoot, 'doctor.mjs')], '启动诊断未通过；请按上方提示处理后重试。')
if (process.argv.includes('--check')) process.exit(0)

run(process.execPath, [join(scriptsRoot, 'cleanup-legacy.mjs')], '清理旧品牌、应用和企业 Tool 配置失败。')
console.log(`QwenPaw 运行环境：${runtime.source === 'project' ? runtime.root : '全局安装'} (${runtime.version})`)
run(qwenpawCommand, ['plugin', 'install', auditPlugin, '--force'], '日志审计插件安装失败。')
run(qwenpawCommand, ['plugin', 'install', logoPlugin, '--force'], 'Logo 配置插件安装失败。')
run(qwenpawCommand, ['plugin', 'install', appDiscoveryPlugin, '--force'], '应用发现插件安装失败。')
run(qwenpawCommand, ['plugin', 'install', dataCorePlugin, '--force'], 'Data Core 插件安装失败。')
run(process.execPath, [join(scriptsRoot, 'sync-pawapps.mjs')], '外部 PawApp 同步失败。')
const externalApps = JSON.parse(readFileSync(pawappsLock, 'utf8')).apps
for (const app of externalApps) {
  const pluginPath = join(appRoot, 'runtime', 'pawapps', app.install_dir)
  run(qwenpawCommand, ['plugin', 'install', pluginPath, '--force'], `${app.id} 应用安装失败。`)
}

console.log('\nAI-OS 启动中：http://127.0.0.1:8088')
console.log(`运行形态：原生 QwenPaw 单进程；启用系统插件与 ${externalApps.length} 个外部 PawApp；不启动企业服务。\n`)
const child = spawn(qwenpawCommand, ['app'], { cwd: repoRoot, stdio: 'inherit', env: launchEnv })
const health = spawn(process.execPath, [join(scriptsRoot, 'health-report.mjs')], {
  cwd: repoRoot,
  stdio: 'inherit',
  env: launchEnv,
})
const modelHealth = spawn(process.execPath, [join(scriptsRoot, 'model-health-report.mjs')], {
  cwd: repoRoot,
  stdio: 'inherit',
  env: launchEnv,
})
process.on('SIGINT', () => {
  health.kill('SIGINT')
  modelHealth.kill('SIGINT')
  child.kill('SIGINT')
})
process.on('SIGTERM', () => {
  health.kill('SIGTERM')
  modelHealth.kill('SIGTERM')
  child.kill('SIGTERM')
})
child.on('exit', code => {
  if (!health.killed) health.kill('SIGTERM')
  if (!modelHealth.killed) modelHealth.kill('SIGTERM')
  process.exitCode = code || 0
})
