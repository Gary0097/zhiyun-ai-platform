# 灵泽万川智造云 AI-OS — QwenPaw Hub 运行环境供给
# 创建/修复 apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv（qwenpaw[hub]==锁版本）。
# start-hub.cmd 在 venv 缺失或版本不符时自动调用本脚本；也可手动运行。
# 模型账号（API Key）由管理员在 Hub 管理界面统一配置（凭据保险库），
# 本脚本只负责运行环境。
[CmdletBinding()]
param([switch]$Offline, [string]$CacheDir = "")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EmbeddedRoot = Join-Path $ProjectRoot "apps\zhizaoyunAIOS"
$Lock = Get-Content -LiteralPath (Join-Path $EmbeddedRoot "qwenpaw.lock.json") -Raw | ConvertFrom-Json
$RuntimeCache = if ($CacheDir) { $CacheDir } else { Join-Path $EmbeddedRoot "runtime\cache" }
$HubVenv = Join-Path $EmbeddedRoot "runtime\qwenpaw-hub\venv"
$HubQwenPaw = Join-Path $HubVenv "Scripts\qwenpaw.exe"
$HubPython = Join-Path $HubVenv "Scripts\python.exe"
$CachedUv = Join-Path $RuntimeCache "bin\uv.exe"

# Hub 控制台品牌化（智造云 AIOS 风格；失败不阻断，可重跑）
function Invoke-HubBranding {
  $PatchScript = Join-Path $ProjectRoot "apps\zhizaoyunAIOS\scripts\patch-console-ui.mjs"
  $HubConsole = Join-Path $HubVenv "Lib\site-packages\qwenpaw\console"
  if ((Test-Path $PatchScript) -and (Test-Path (Join-Path $HubConsole "index.html"))) {
    try { & node $PatchScript --console-dir $HubConsole | Out-Null } catch { Write-Host "提示：Hub 控制台品牌化未完成，可重跑 setup-hub.ps1。" }
  }
}

function Test-HubRuntime {
  if (-not (Test-Path -LiteralPath $HubQwenPaw) -or -not (Test-Path -LiteralPath $HubPython)) { return $false }
  # 经 cmd 隔离探测：venv 损坏时 uv trampoline 会写 stderr，EAP=Stop 下
  # 直接调用会把它升级为终止性错误（setup-ai-os.ps1 注释中的同一陷阱）
  $versionOutput = & cmd.exe /d /c "`"$HubQwenPaw`" --version 2>&1" | Out-String
  return $LASTEXITCODE -eq 0 -and $versionOutput -match ("version\s+" + [regex]::Escape($Lock.version) + "\s*$")
}
if (Test-HubRuntime) {
  Write-Host "QwenPaw Hub $($Lock.version) 运行环境已就绪：$HubVenv"
  Invoke-HubBranding
  exit 0
}

$UvCommand = if (Test-Path -LiteralPath $CachedUv) { $CachedUv } else { (Get-Command uv -ErrorAction SilentlyContinue).Source }
if (-not $UvCommand) {
  if ($Offline) { throw "离线缓存中没有 uv：$CachedUv。请先在联网环境运行一次安装。" }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CachedUv) | Out-Null
  $bootstrap = Join-Path $RuntimeCache "uv-install.ps1"
  Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $bootstrap -UseBasicParsing
  $env:UV_INSTALL_DIR = Split-Path -Parent $CachedUv
  $env:UV_NO_MODIFY_PATH = "1"
  & $bootstrap
  $UvCommand = $CachedUv
}

$previous = @{
  UV_CACHE_DIR = $env:UV_CACHE_DIR; UV_PYTHON_INSTALL_DIR = $env:UV_PYTHON_INSTALL_DIR
  UV_PYTHON_PREFERENCE = $env:UV_PYTHON_PREFERENCE; UV_OFFLINE = $env:UV_OFFLINE
}
try {
  $env:UV_CACHE_DIR = Join-Path $RuntimeCache "uv"
  $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeCache "python"
  $env:UV_PYTHON_PREFERENCE = "only-managed"
  if ($Offline) { $env:UV_OFFLINE = "1" }
  & $UvCommand venv $HubVenv --python 3.12 --clear
  if ($LASTEXITCODE -ne 0) { throw "uv venv 退出码：$LASTEXITCODE" }
  & $UvCommand pip install --python $HubPython "qwenpaw[hub]==$($Lock.version)"
  if ($LASTEXITCODE -ne 0) { throw "uv pip install qwenpaw[hub] 退出码：$LASTEXITCODE（离线包需先在联网环境预置 hub 依赖缓存）" }
} finally {
  foreach ($name in $previous.Keys) { Set-Item -Path "env:$name" -Value $previous[$name] }
}
if (-not (Test-HubRuntime)) { throw "QwenPaw Hub 运行环境安装后版本校验失败。" }

Invoke-HubBranding
Write-Host "QwenPaw Hub $($Lock.version) 运行环境安装完成：$HubVenv"
