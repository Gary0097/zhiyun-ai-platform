# 灵泽万川智造云 AI-OS — 桌面/开始菜单快捷方式（Edge/Chrome 应用模式窗口）
# 在线安装流程调用：双击快捷方式 = 无地址栏独立窗口打开 Console。
# 打包离线流程不使用本脚本（快捷方式由安装引导器指向桌面启动器 exe）。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-desktop-shortcut.ps1 [-InstallDir <目录>]
param(
    [string]$InstallDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$browsers = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
)
$browser = $browsers | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    Write-Host "[提示] 未找到 Edge/Chrome，跳过快捷方式创建（可手动收藏 http://127.0.0.1:8088）。"
    exit 0
}

$icon = Join-Path $InstallDir 'branding\app.ico'
if (-not (Test-Path $icon)) { $icon = $null }

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) '智造云 AI-OS.lnk'),
    (Join-Path ($env:APPDATA + '\Microsoft\Windows\Start Menu\Programs') '智造云 AI-OS.lnk')
)
foreach ($lnk in $targets) {
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $browser
    $sc.Arguments = '--app=http://127.0.0.1:8088'
    $sc.WorkingDirectory = $InstallDir
    $sc.Description = '灵泽万川智造云 AI-OS'
    if ($icon) { $sc.IconLocation = "$icon,0" }
    $sc.Save()
}
Write-Host "[完成] 已创建桌面与开始菜单快捷方式（双击即以应用窗口打开）。"
