import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import net from 'node:net'
import { resolveRuntime, runtimeEnvironment, listenPort } from './runtime-env.mjs'
import { diagnose } from './doctor.mjs'

// 智造云 AIOS 2.2.2 —— 原生 QwenPaw 2.2.2 启动器（无捆绑业务应用）
// 形态：原生 QwenPaw 单进程 + 控制台原生登录（QWENPAW_AUTH_ENABLED）。
// 多用户/集中模型账号请使用 start-hub.cmd（QwenPaw Hub）。
const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = join(appRoot, '..', '..')
const scriptsRoot = join(appRoot, 'scripts')
const port = listenPort(process.env.AIOS_PORT)
const runtime = resolveRuntime()
const launchEnv = runtimeEnvironment(runtime)
const qwenpawCommand = runtime.command || 'qwenpaw'

Object.assign(launchEnv, {
  QWENPAW_WORKING_DIR: join(appRoot, 'workspace'),
  // 登录体系改用 QwenPaw 2.2.2 原生认证：首个用户在控制台注册，
  // 之后所有访问均需登录（多用户场景由 Hub 账号体系承载）
  QWENPAW_AUTH_ENABLED: 'true',
  // 原生认证密钥固定在安装目录内（auth.json / API Key 等），
  // 避免落到用户主目录 ~/.qwenpaw.secret，与 README 的数据边界声明一致
  QWENPAW_SECRET_DIR: process.env.QWENPAW_SECRET_DIR || join(appRoot, 'workspace', 'secret'),
})

function run (command, args, hint) {
  const result = spawnSync(command, args, { cwd: repoRoot, stdio: 'inherit', env: launchEnv })
  if (result.error || result.status !== 0) {
    console.error(`子进程失败：${result.error?.message || result.signal || 'exit ' + result.status}`)
    console.error(`\n${hint}`)
    process.exit(result.status || 1)
  }
}

// 升级/重复启动接管：8088 若被“我们自己的实例”（可执行文件路径含
// zhizaoyunAIOS / qwenpaw）占用，直接停掉旧进程再启动。外来进程不动，
// 交给 doctor 的端口检查报错。
async function stopStaleInstance () {
  if (process.platform !== 'win32') return false
  // Most starts have no listener. Avoid loading PowerShell/NetTCPIP just to
  // discover an unused port; ownership checks below remain mandatory if busy.
  const listening = await new Promise(resolve => {
    const socket = net.createConnection({ host: '127.0.0.1', port })
    socket.setTimeout(300)
    socket.once('connect', () => { socket.destroy(); resolve(true) })
    socket.once('error', () => { socket.destroy(); resolve(false) })
    socket.once('timeout', () => { socket.destroy(); resolve(true) })
  })
  if (!listening) return false
  const probe = spawnSync('powershell', ['-NoProfile', '-Command',
    `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess`], { encoding: 'utf8' })
  const pid = parseInt((probe.stdout || '').trim(), 10)
  if (!pid || Number.isNaN(pid)) return false
  const pathProbe = spawnSync('powershell', ['-NoProfile', '-Command',
    `(Get-Process -Id ${pid} -ErrorAction SilentlyContinue).Path`], { encoding: 'utf8' })
  const ownerPath = (pathProbe.stdout || '').trim()
  if (!ownerPath) return false
  if (!resolve(ownerPath).toLowerCase().startsWith((resolve(repoRoot) + sep).toLowerCase())) return false
  console.log(`检测到本平台旧实例（PID ${pid}），自动停止以完成升级/重启…`)
  spawnSync('powershell', ['-NoProfile', '-Command',
    `try { Stop-Process -Id ${pid} -Force } catch {}`])
  for (let i = 0; i < 10; i++) {
    const check = spawnSync('powershell', ['-NoProfile', '-Command',
      `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue) -ne $null`], { encoding: 'utf8' })
    if ((check.stdout || '').trim() !== 'True') return true
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500)
  }
  return true
}

if (!process.argv.includes('--check')) {
  try { await stopStaleInstance() } catch (e) { console.warn('旧实例接管检查失败：', e.message) }
}

// Reuse the validated object in this process, never an environment-supplied receipt.
if (await diagnose({ runtime, port }) !== 0) process.exit(1)
if (process.argv.includes('--check')) process.exit(0)

run(process.execPath, [join(scriptsRoot, 'ensure-workspace.mjs')], 'Workspace 初始化失败。')
if (existsSync(join(scriptsRoot, 'patch-console-ui.mjs'))) {
  const consoleDir = process.platform === 'win32' && runtime.python
    ? join(dirname(runtime.python), '..', 'Lib', 'site-packages', 'qwenpaw', 'console') : null
  const args = [join(scriptsRoot, 'patch-console-ui.mjs')]
  if (consoleDir && existsSync(join(consoleDir, 'index.html'))) args.push('--console-dir', consoleDir)
  run(process.execPath, args, 'Console UI 品牌化脚本执行失败。')
}

// ensure-workspace synchronizes the sanctioned frontend tree. The native
// loader discovers it at boot; a separate CLI installation is unnecessary.
const brandPlugin = join(repoRoot, 'plugins', 'aios-brand')
if (existsSync(join(brandPlugin, 'plugin.json'))) {
  const brandVersion = JSON.parse(readFileSync(join(brandPlugin, 'plugin.json'), 'utf8')).version
  const brandMarker = join(appRoot, 'workspace', '.brand-plugin.version')
  const installedManifest = join(appRoot, 'workspace', 'plugins', 'aios-brand', 'plugin.json')
  if (existsSync(installedManifest) && JSON.parse(readFileSync(installedManifest, 'utf8')).version === brandVersion) {
    if (!existsSync(brandMarker) || readFileSync(brandMarker, 'utf8').trim() !== brandVersion) {
      writeFileSync(brandMarker, brandVersion + '\n', 'utf8')
    }
    console.log(`品牌前端 v${brandVersion} 已同步，由原生加载器发现，无需安装子进程。`)
  } else {
    console.warn('品牌前端文件尚未同步，外观回退为补丁层。')
  }
}

console.log(`\n智造云 AIOS 启动中：http://127.0.0.1:${port}`)
console.log('运行形态：原生 QwenPaw 2.2.2 单进程；控制台原生登录；无捆绑业务应用。')
console.log('多用户/集中模型账号：运行 start-hub.cmd（QwenPaw Hub，端口 8000）。\n')
const child = spawn(qwenpawCommand, ['app', '--port', String(port)], { cwd: repoRoot, stdio: 'inherit', env: launchEnv })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('exit', code => { process.exitCode = code || 0 })
