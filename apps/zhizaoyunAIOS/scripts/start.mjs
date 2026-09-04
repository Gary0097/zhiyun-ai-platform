import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveRuntime, runtimeEnvironment } from './runtime-env.mjs'

// 智造云 AIOS 2.2.0 —— 原生 QwenPaw 2.2.0 启动器（无捆绑业务应用）
// 形态：原生 QwenPaw 单进程 + 控制台原生登录（QWENPAW_AUTH_ENABLED）。
// 多用户/集中模型账号请使用 start-hub.cmd（QwenPaw Hub）。
const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const scriptsRoot = join(appRoot, 'scripts')
const runtime = resolveRuntime()
const launchEnv = runtimeEnvironment(runtime)
const qwenpawCommand = runtime.command || 'qwenpaw'

Object.assign(launchEnv, {
  QWENPAW_WORKING_DIR: join(appRoot, 'workspace'),
  // 登录体系改用 QwenPaw 2.2.0 原生认证：首个用户在控制台注册，
  // 之后所有访问均需登录（多用户场景由 Hub 账号体系承载）
  QWENPAW_AUTH_ENABLED: 'true',
})

function run (command, args, hint) {
  const result = spawnSync(command, args, { cwd: repoRoot, stdio: 'inherit', env: launchEnv })
  if (result.error || result.status !== 0) {
    console.error(`\n${hint}`)
    process.exit(result.status || 1)
  }
}

// 升级/重复启动接管：8088 若被“我们自己的实例”（可执行文件路径含
// zhizaoyunAIOS / qwenpaw）占用，直接停掉旧进程再启动。外来进程不动，
// 交给 doctor 的端口检查报错。
function stopStaleInstance () {
  const probe = spawnSync('powershell', ['-NoProfile', '-Command',
    "(Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"], { encoding: 'utf8' })
  const pid = parseInt((probe.stdout || '').trim(), 10)
  if (!pid || Number.isNaN(pid)) return false
  const pathProbe = spawnSync('powershell', ['-NoProfile', '-Command',
    `(Get-Process -Id ${pid} -ErrorAction SilentlyContinue).Path`], { encoding: 'utf8' })
  const ownerPath = (pathProbe.stdout || '').trim()
  if (!ownerPath) return false
  if (!/zhizaoyunAIOS|qwenpaw/i.test(ownerPath)) return false // 非本平台进程：不接管
  console.log(`检测到本平台旧实例（PID ${pid}），自动停止以完成升级/重启…`)
  spawnSync('powershell', ['-NoProfile', '-Command',
    `try { Stop-Process -Id ${pid} -Force } catch {}`])
  for (let i = 0; i < 10; i++) {
    const check = spawnSync('powershell', ['-NoProfile', '-Command',
      "(Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) -ne $null"], { encoding: 'utf8' })
    if ((check.stdout || '').trim() !== 'True') return true
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500)
  }
  return true
}

try { stopStaleInstance() } catch (e) { console.warn('旧实例接管检查失败：', e.message) }

run(process.execPath, [join(scriptsRoot, 'doctor.mjs')], '启动诊断未通过；请按上方提示处理后重试。')
if (process.argv.includes('--check')) process.exit(0)

run(process.execPath, [join(scriptsRoot, 'ensure-workspace.mjs')], 'Workspace 初始化失败。')
if (existsSync(join(scriptsRoot, 'patch-console-ui.mjs'))) {
  run(process.execPath, [join(scriptsRoot, 'patch-console-ui.mjs')], 'Console UI 品牌化脚本执行失败。')
}

console.log('\n智造云 AIOS 启动中：http://127.0.0.1:8088')
console.log('运行形态：原生 QwenPaw 2.2.0 单进程；控制台原生登录；无捆绑业务应用。')
console.log('多用户/集中模型账号：运行 start-hub.cmd（QwenPaw Hub，端口 8000）。\n')
const child = spawn(qwenpawCommand, ['app'], { cwd: repoRoot, stdio: 'inherit', env: launchEnv })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('exit', code => { process.exitCode = code || 0 })
