// 构建一键安装发布包：从干净的 worktree 导出受控文件 + 版本清单，输出 zip 与 SHA256。
// 前置：发布内容已合并到目标分支。用法：
//   node scripts/make-release-package.mjs <版本号> [--offline] [--ref <ref>] [--no-prune]
// --offline：U盘离线安装包 —— 额外内嵌 Python 运行时缓存（runtime/cache）、
//   锁定 PawApp（runtime/pawapps）与便携 node.exe（extras/node），
//   目标机器解压后运行 install-usb.cmd 即可，全程无需联网。
// --no-prune：跳过 dist 历史产物清理（默认打包成功后只保留最近 2 个版本）。
import { createHash } from 'node:crypto'
import { execSync, execFileSync } from 'node:child_process'
import { mkdirSync, copyFileSync, readFileSync, writeFileSync, existsSync, statSync, rmSync, cpSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { pruneDist } from './release-prune.mjs'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const argv = process.argv.slice(2)
const version = argv.find(a => !a.startsWith('--')) || process.env.RELEASE_VERSION || ''
const offline = argv.includes('--offline')
const refFlagIdx = argv.indexOf('--ref')
const ref = refFlagIdx !== -1 ? argv[refFlagIdx + 1] : (process.env.RELEASE_REF || 'master')
if (!version) {
  console.error('用法：node scripts/make-release-package.mjs <版本号> [--offline] [--ref <ref>]，如 1.2.0')
  process.exit(1)
}
const distDir = join(root, 'dist')
const zipName = `zhiyun-ai-os-v${version}-${offline ? 'offline-usb' : 'online-installer'}.zip`
const zipPath = join(distDir, zipName)
const workDir = join(root, '.release-worktree')

function run(cmd, opts = {}) { execSync(cmd, { cwd: root, stdio: 'inherit', ...opts }) }
function dirSizeMb (p) {
  let total = 0
  const walk = d => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const f = join(d, e.name)
      try {
        if (e.isDirectory() && !e.isSymbolicLink()) walk(f)
        else total += statSync(f).size
      } catch { /* 断链/权限抖动跳过 */ }
    }
  }
  if (existsSync(p)) walk(p)
  return (total / 1024 / 1024).toFixed(0)
}

rmSync(workDir, { recursive: true, force: true })
mkdirSync(distDir, { recursive: true })
// 残留注册清理：rmSync 只删目录不清注册表，会导致下一次 add 报
// "missing but already registered"（曾连续卡死打包）。
try { run(`git worktree remove --force "${workDir}"`) } catch { /* 未注册时忽略 */ }
run(`git worktree prune`)
run(`git worktree add --detach "${workDir}" ${ref}`)

// 版本清单：运行时版本随包分发，供校验与诊断
const pawappsLockPath = join(workDir, 'apps', 'zhizaoyunAIOS', 'pawapps.lock.json')
const pawappsLock = existsSync(pawappsLockPath)
  ? JSON.parse(readFileSync(pawappsLockPath, 'utf8'))
  : { apps: [] }
// 运行时版本以被打包 ref 的锁为准（--ref 重建旧版本时清单不得错报）
const qwenpawLock = JSON.parse(readFileSync(join(workDir, 'apps', 'zhizaoyunAIOS', 'qwenpaw.lock.json'), 'utf8'))
const manifest = [
  'product: zhiyun-ai-os',
  `version: ${version}`,
  `qwenpaw: ${qwenpawLock.version}`,
  `locked_pawapps: ${pawappsLock.apps.length}`,
  ...pawappsLock.apps.map(a => `  - ${a.id} @ ${a.commit}`),
  `channel: ${offline ? 'offline-usb' : 'online-installer'}`,
  offline
    ? 'note: U盘离线安装包 —— 内嵌 Python 运行时缓存、锁定 PawApp 与便携 Node；解压后运行 install-usb.cmd'
    : 'note: 首次运行 install-oneclick 时会从 GitHub 拉取以上锁定版本',
]
writeFileSync(join(workDir, 'INSTALLER-VERSION.txt'), manifest.join('\n') + '\n', 'utf8')

if (offline) {
  // 0) 离线包标记：start-hub.cmd/sh 据此对 Hub 运行环境使用离线安装，
  //    避免源码/在线安装被误设离线模式后首次启动失败
  mkdirSync(join(workDir, 'apps', 'zhizaoyunAIOS', 'runtime', 'cache'), { recursive: true })
  writeFileSync(join(workDir, 'apps', 'zhizaoyunAIOS', 'runtime', 'cache', 'OFFLINE-PACKAGE'), 'offline-usb' + String.fromCharCode(10), 'utf8')
  // 1) 内嵌运行时缓存（Python 3.12 + uv + wheel 缓存）与锁定 PawApp
  const liveRuntime = join(root, 'apps', 'zhizaoyunAIOS', 'runtime')
  const pkgRuntime = join(workDir, 'apps', 'zhizaoyunAIOS', 'runtime')
  // 2.2.0 极简形态无捆绑 PawApp；pawapps 锁不存在时跳过物料嵌入
  for (const part of existsSync(pawappsLockPath) ? ['cache', 'pawapps'] : ['cache']) {
    const src = join(liveRuntime, part)
    if (!existsSync(src)) {
      console.error(`离线包缺少 ${src}；请先在本机完成一次在线安装。`)
      process.exit(1)
    }
    // 离线硬依赖防呆：uv 引导器与 Python 运行时缺失会让目标机器在 setup
    // 早期就失败（v1.3.3 事故：cache/bin 被清后照常打包）。
    if (part === 'cache') {
      for (const required of ['bin/uv.exe', 'python']) {
        if (!existsSync(join(src, required))) {
          console.error(`离线缓存缺少硬依赖 ${required}（${join(src, required)}）；中止打包。`)
          process.exit(1)
        }
      }
    }
    console.log(`内嵌 runtime/${part}（${dirSizeMb(src)} MB）...`)
    cpSync(src, join(pkgRuntime, part), { recursive: true })
  }
  // 2) 便携 Node（仅 node.exe，约 80MB；start-ai-os.cmd 会自动优先使用）
  const nodeSrc = process.env.NODE_SRC || join(process.env.ProgramFiles || 'C:\\Program Files', 'nodejs', 'node.exe')
  if (existsSync(nodeSrc)) {
    mkdirSync(join(workDir, 'extras', 'node'), { recursive: true })
    copyFileSync(nodeSrc, join(workDir, 'extras', 'node', 'node.exe'))
    console.log(`内嵌便携 Node：${nodeSrc}`)
  } else {
    console.warn('警告：未找到 node.exe，离线包将要求目标机器自行安装 Node.js 20+。')
  }
  // 3) U盘一键安装入口（自动优先使用内嵌 node）
  // cmd 在中文系统默认 GBK 代码页，UTF-8 中文 echo 会被误读成乱码命令
  // （曾出现 '锟藉姩...' not recognized），因此批处理输出一律用 ASCII。
  writeFileSync(join(workDir, 'install-usb.cmd'), [
    '@echo off',
    'chcp 65001 >nul',
    'title Lingze Wanchuan Zhizaoyun AI-OS - USB Offline Setup',
    'cd /d "%~dp0"',
    // 覆盖升级：停止本安装实例（8088 监听须命令行包含本安装目录 %~dp0 才杀，
    // 避免误伤其他 QwenPaw/智造云安装或占用该端口的无关应用；同时结束驻留托盘
    // exe 以解锁升级解压）
    'powershell -NoProfile -Command "$root=[regex]::Escape(\'%~dp0\'); Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-CimInstance Win32_Process -Filter (\'ProcessId=\' + $_.OwningProcess); if ($p -and $p.CommandLine -match $root) { Stop-Process -Id $p.ProcessId -Force } }" >nul 2>&1',
    "powershell -NoProfile -Command \"Get-Process -Name '智造云AI-OS' -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '%~dp0*' } | Stop-Process -Force\" >nul 2>&1",
    'echo ==============================================',
    'echo   Lingze Wanchuan Zhizaoyun AI-OS - USB offline install',
    'echo   Auto-starts and opens the browser when finished.',
    'echo   (Chinese guide: see USB-INSTALL.md)',
    'echo ==============================================',
    'echo.',
    'if exist "extras\\node\\node.exe" set "PATH=%~dp0extras\\node;%PATH%"',
    'where node >nul 2>nul',
    'if errorlevel 1 (',
    '  echo [错误] 未找到 Node.js：本包未内嵌 node.exe 时需要目标机器安装 Node.js 20+。',
    '  echo 下载地址：https://nodejs.org/zh-cn',
    '  pause',
    '  exit /b 1',
    ')',
    'powershell -NoProfile -ExecutionPolicy Bypass -File setup-ai-os.ps1 -Offline -CacheDir "apps\\zhizaoyunAIOS\\runtime\\cache"',
    'if errorlevel 1 ( echo [错误] 运行环境安装失败，请检查上方输出。 & pause & exit /b 1 )',
    'powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) { exit 1 }" >nul 2>&1',
    'if errorlevel 1 ( echo [错误] 端口 8088 仍被其他应用占用，请先释放该端口再安装。 & pause & exit /b 1 )',
    'rem 优先用桌面启动器（闪屏→服务就绪→Edge 应用窗口）；无 exe 时回退控制台启动',
    'if exist "智造云AI-OS.exe" ( start "" "智造云AI-OS.exe" ) else ( call start-ai-os.cmd )',
    '',
  ].join('\r\n'), 'utf8')
  // 5) 桌面启动器 exe（品牌图标，安装后快捷方式与 install-usb 末尾均指向它；
  //    仅 Windows 打包机可编译，其他平台跳过并在安装时回退 .cmd 启动）
  if (process.platform === 'win32') {
    const cscCandidates = [
      join(process.env.SystemRoot || 'C:\\Windows', 'Microsoft.NET', 'Framework64', 'v4.0.30319', 'csc.exe'),
      join(process.env.SystemRoot || 'C:\\Windows', 'Microsoft.NET', 'Framework', 'v4.0.30319', 'csc.exe'),
    ]
    const csc = cscCandidates.find(existsSync)
    const iconPath = join(workDir, 'branding', 'app.ico')
    if (csc && existsSync(iconPath)) {
      const launcherExe = join(workDir, '智造云AI-OS.exe')
      const launcherSrc = join(workDir, 'scripts', 'exe-installer', 'launcher.cs')
      execFileSync(csc, [
        '/nologo', '/target:winexe', '/optimize+',
        '/out:' + launcherExe,
        '/win32icon:' + iconPath,
        '/r:System.Windows.Forms.dll',
        '/r:System.Drawing.dll',
        launcherSrc,
      ], { stdio: 'inherit' })
      console.log(`内嵌桌面启动器：智造云AI-OS.exe（v${version}）`)
    } else {
      console.warn('警告：未找到 csc.exe 或 branding/app.ico，离线包不含桌面启动器（安装时回退 .cmd 启动）。')
    }
  } else {
    console.warn('警告：非 Windows 打包机，离线包不含桌面启动器 exe（安装时回退 .cmd 启动）。')
  }
  // 4) 中文安装说明（带 BOM，记事本直接可读）
  const guide = [
    '# 灵泽万川智造云 AI-OS — U盘离线安装说明',
    '',
    '1. 把整个文件夹（或 zip）拷到目标电脑任意可写目录，解压。',
    '2. 双击 `install-usb.cmd`：自动使用包内 Python/Node 运行时，无需联网。',
    '3. 安装完成会自动启动服务并打开浏览器（默认 http://127.0.0.1:8088）。',
    '4. 首次使用：打开 http://127.0.0.1:8088 注册账号（第一个注册的账号即管理员，',
    '   请设置高强度密码；后续用户在登录页自行注册）。',
    '5. 局域网多用户：运行 `start-hub.cmd` 启动 Hub（0.0.0.0:8000），模型账号',
    '   （API Key）由管理员在 Hub 管理界面统一配置。',
    '6. 忘记密码：停止服务后删除服务数据目录下的 `auth.json`，重启后重新注册',
    '   （官方文档提供的重置方式，会清除全部本地账户）。',
    '',
    '常用入口：start-ai-os.cmd（启动）、diagnose-ai-os.cmd（诊断）、',
    'start-hub.cmd（局域网多用户，0.0.0.0:8000）。',
    '',
    '要求：Windows 10/11 x64；本包未内嵌 node.exe 时需 Node.js 20+。',
    '',
  ].join('\r\n')
  writeFileSync(join(workDir, 'USB-INSTALL.md'), '\uFEFF' + guide, 'utf8')
}

// 先移除 worktree 的 .git 指针（文件或目录），避免压缩包泄漏本机绝对路径
const gitEntry = join(workDir, '.git')
if (existsSync(gitEntry)) {
  const st = statSync(gitEntry)
  if (st.isDirectory()) rmSync(gitEntry, { recursive: true, force: true })
  else rmSync(gitEntry, { force: true })
}

try {
  // 跨平台压缩：优先系统 bsdtar（Windows 10+ 自带，大目录远快于 Compress-Archive）
  const windowsTar = join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe')
  if (process.platform === 'win32' && existsSync(windowsTar)) {
    run(`"${windowsTar}" -a -c -f "${zipPath}" -C "${workDir}" .`)
  } else if (process.platform === 'win32') {
    run(`powershell -NoProfile -Command "Compress-Archive -Path '${join(workDir, '*')}' -DestinationPath '${zipPath}' -Force"`)
  } else {
    run(`cd "${workDir}" && zip -r -q "${zipPath}" . -x '.git'`)
  }
} finally {
  // 无论成败都清理 worktree（失败后 prune，保证下次可重建）
  try { run('git worktree remove --force .release-worktree') } catch { run('git worktree prune'); rmSync(workDir, { recursive: true, force: true }) }
}

const sha256 = createHash('sha256').update(readFileSync(zipPath)).digest('hex')
writeFileSync(`${zipPath}.sha256`, `${sha256}  ${zipName}\n`, 'utf8')
writeFileSync(join(distDir, 'INSTALLER-VERSION.txt'), manifest.join('\n') + '\n', 'utf8')
const sizeMb = (statSync(zipPath).size / 1024 / 1024).toFixed(2)
console.log(`打包完成：dist/${zipName}（${sizeMb} MB）`)
console.log(`SHA256：${sha256}`)
if (!existsSync(zipPath) || statSync(zipPath).size < 50 * 1024) {
  console.error('打包产物异常（过小），请检查压缩步骤。')
  process.exit(1)
}

// 打包成功后再清理历史产物，失败路径绝不删除任何旧版本；
// protect 保证 --ref 重建旧版本时本次刚构建的产物不会被当作历史清理掉
if (!argv.includes('--no-prune')) {
  for (const name of pruneDist(distDir, { keep: 2, protect: version })) console.log(`清理历史产物：${name}`)
}
// 后置保险：清理后本次产物必须仍在，否则视为清理故障
if (!existsSync(zipPath)) {
  console.error('清理步骤误删了本次构建产物，请检查 release-prune 的 protect 参数。')
  process.exit(1)
}
