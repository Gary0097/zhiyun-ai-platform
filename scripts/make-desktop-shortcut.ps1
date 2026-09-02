# 灵泽万川智造云 AI-OS — 桌面/开始菜单快捷方式（在线安装流程）
# 生成"智造云AI-OS启动.cmd"包装脚本：服务未运行时自动拉起 → 探活就绪 →
# 以 Edge/Chrome 应用模式（无地址栏独立窗口）打开 Console。快捷方式指向
# 该包装脚本并使用品牌图标，重启后双击仍可用。
# 打包离线流程不使用本脚本（离线快捷方式由安装引导器指向桌面启动器 exe）。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-desktop-shortcut.ps1 [-InstallDir <目录>]
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# 1) 探测可用的应用模式浏览器（Edge/Chrome），写入包装脚本
$edgeX86 = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$edgeX64 = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
$chromeLocal = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
$chromeX64 = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"

$openLine = 'start "" "http://127.0.0.1:8088"'
foreach ($candidate in @($edgeX86, $edgeX64, $chromeLocal, $chromeX64)) {
    if ($candidate -and (Test-Path $candidate)) {
        $openLine = 'start "" "' + $candidate + '" --app=http://127.0.0.1:8088'
        break
    }
}

# 2) 生成包装脚本（内容 ASCII，cmd 安全；UTF-8 无 BOM）
$wrapper = Join-Path $InstallDir '智造云AI-OS启动.cmd'
$lines = @(
    '@echo off',
    'chcp 65001 >nul',
    'title Lingze Wanchuan Zhizaoyun AI-OS',
    'cd /d "%~dp0"',
    'rem 1) service already listening on 8088?',
    'netstat -ano | findstr :8088 | findstr LISTENING >nul 2>nul',
    'if errorlevel 1 (',
    '  echo Starting service (first launch takes 1-3 minutes)...',
    '  start "zhizaoyun-service" /min cmd /c "start-ai-os.cmd >> launcher-service.log 2>&1"',
    ')',
    'rem 2) wait for /api/version readiness (up to ~5 minutes)',
    'powershell -NoProfile -Command "for($i=0;$i -lt 150;$i++){ try { Invoke-WebRequest -Uri ''http://127.0.0.1:8088/api/version'' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep 2 } }; exit 1"',
    'if errorlevel 1 (',
    '  echo Service did not become ready. Check launcher-service.log',
    '  pause',
    '  exit /b 1',
    ')',
    'rem 3) open app-mode window',
    $openLine,
    ''
)
[System.IO.File]::WriteAllLines($wrapper, $lines, (New-Object System.Text.UTF8Encoding($false)))

# 3) 创建桌面与开始菜单快捷方式：指向包装脚本，图标用随仓库分发的品牌 ico
$icon = Join-Path $InstallDir 'branding\app.ico'
if (-not (Test-Path $icon)) { $icon = $wrapper }

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) '智造云 AI-OS.lnk'),
    (Join-Path ($env:APPDATA + '\Microsoft\Windows\Start Menu\Programs') '智造云 AI-OS.lnk')
)
foreach ($lnk in $targets) {
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $wrapper
    $sc.WorkingDirectory = $InstallDir
    $sc.Description = '灵泽万川智造云 AI-OS'
    $sc.IconLocation = "$icon,0"
    $sc.Save()
}
Write-Host "[完成] 已创建桌面与开始菜单快捷方式（自动起服务并以应用窗口打开）。"
