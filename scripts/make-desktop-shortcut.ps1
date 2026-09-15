# 灵泽万川智造云 AI-OS — 桌面/开始菜单快捷方式（在线安装流程）
# 生成两个文件：
#   ensure-ai-os-service.ps1 —— 互斥串行化 + 归属校验 + 拉起服务 + 就绪等待
#   智造云AI-OS启动.cmd —— 调用 ensure 脚本，就绪后以 Edge/Chrome 应用窗口打开
# 归属校验绑定本安装目录（命令行含该目录），不会把其他 QwenPaw 安装或
# 无关应用误认成"自己的"；互斥串行化避免启动期两条管线并发执行工作区变更。
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

# 2) 生成 ensure-ai-os-service.ps1（互斥 + 归属校验 + 拉起 + 就绪等待）
#    退出码：0=就绪 1=未就绪 3=端口被无关应用占用
$ensure = Join-Path $InstallDir 'ensure-ai-os-service.ps1'
$ensureBody = @'
# 自动生成：make-desktop-shortcut.ps1
param(
    [string]$Root = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)
$ErrorActionPreference = 'Stop'
$root = [regex]::Escape($Root)
$m = New-Object System.Threading.Mutex($false, 'Local\ZhizaoyunAIOS.OnlineStart')
$owned = $false
try {
    try { [void]$m.WaitOne(20000); $owned = $true }
    catch [System.Threading.AbandonedMutexException] { $owned = $true }
    $c = Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) {
        $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess)
        if (-not ($p -and $p.CommandLine -match $root)) {
            Write-Host '[ERROR] Port 8088 is occupied by another application.'
            exit 3
        }
        # 本安装已在运行，无需拉起
        exit 0
    }
    Start-Process -FilePath (Join-Path $Root 'start-ai-os.cmd') -WindowStyle Hidden
    # 就绪等待必须仍在互斥区内：若拉起后立即释放，第二次调用的快捷方式会
    # 在服务绑定 8088 前拿到互斥体并再起一条完整启动管线（并发改工作区）。
    for ($i = 0; $i -lt 150; $i++) {
        try {
            Invoke-WebRequest -Uri 'http://127.0.0.1:8088/api/version' -UseBasicParsing -TimeoutSec 2 | Out-Null
            exit 0
        } catch { Start-Sleep 2 }
    }
    Write-Host '[ERROR] Service did not become ready. See launcher-service.log'
    exit 1
}
finally {
    if ($owned) { $m.ReleaseMutex() }
}
'@
[System.IO.File]::WriteAllText($ensure, $ensureBody, (New-Object System.Text.UTF8Encoding($false)))

# 3) 生成包装脚本（内容 ASCII，cmd 安全；UTF-8 无 BOM）
$wrapper = Join-Path $InstallDir '智造云AI-OS启动.cmd'
$lines = @(
    '@echo off',
    'chcp 65001 >nul',
    'title Lingze Wanchuan Zhizaoyun AI-OS',
    'cd /d "%~dp0"',
    'rem ensure service (mutex-serialized, ownership-checked, wait-ready)',
    'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure-ai-os-service.ps1" -Root "%~dp0"',
    'if errorlevel 3 (',
    '  echo [ERROR] Port 8088 is occupied by another application.',
    '  echo Run diagnose-ai-os.cmd for details.',
    '  pause',
    '  exit /b 1',
    ')',
    'if errorlevel 1 (',
    '  echo Service did not become ready. Check launcher-service.log',
    '  pause',
    '  exit /b 1',
    ')',
    'rem open app-mode window',
    $openLine,
    ''
)
[System.IO.File]::WriteAllLines($wrapper, $lines, (New-Object System.Text.UTF8Encoding($false)))

# 4) 创建桌面与开始菜单快捷方式：指向包装脚本，图标用随仓库分发的品牌 ico
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
