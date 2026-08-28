[CmdletBinding()]
param([switch]$Offline, [string]$CacheDir = "")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EmbeddedRoot = Join-Path $ProjectRoot "apps\qwenpaw-embedded"
$Lock = Get-Content -LiteralPath (Join-Path $EmbeddedRoot "qwenpaw.lock.json") -Raw | ConvertFrom-Json
$RuntimeRoot = Join-Path $EmbeddedRoot ($Lock.runtime_dir -replace '/', '\')
$RuntimeCache = if ($CacheDir) { $CacheDir } else { Join-Path $EmbeddedRoot "runtime\cache" }
$VenvRoot = Join-Path $RuntimeRoot "venv"
$QwenPawCommand = Join-Path $VenvRoot "Scripts\qwenpaw.exe"
$PythonCommand = Join-Path $VenvRoot "Scripts\python.exe"
$CachedUv = Join-Path $RuntimeCache "bin\uv.exe"

function Test-QwenPawRuntime {
  if (-not (Test-Path -LiteralPath $QwenPawCommand) -or -not (Test-Path -LiteralPath $PythonCommand)) { return $false }
  $venvConfig = Get-Content -LiteralPath (Join-Path $VenvRoot "pyvenv.cfg") -ErrorAction SilentlyContinue
  $pythonHome = ($venvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1) -replace '^home\s*=\s*', ''
  if ($pythonHome -match '\\Microsoft\\WindowsApps\\') { return $false }
  if (-not $pythonHome -or -not (Test-Path -LiteralPath (Join-Path $pythonHome "python.exe"))) { return $false }
  & cmd.exe /d /c "`"$PythonCommand`" --version >nul 2>&1"
  if ($LASTEXITCODE -ne 0) { return $false }
  $versionOutput = & $QwenPawCommand --version 2>&1 | Out-String
  return $LASTEXITCODE -eq 0 -and $versionOutput -match ("version\s+" + [regex]::Escape($Lock.version) + "\s*$")
}
if (Test-QwenPawRuntime) { Write-Host "QwenPaw $($Lock.version) 项目运行环境已就绪：$RuntimeRoot"; exit 0 }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CachedUv), (Join-Path $RuntimeCache "uv"), (Join-Path $RuntimeCache "python") | Out-Null
$UvCommand = if (Test-Path -LiteralPath $CachedUv) { $CachedUv } else { (Get-Command uv -ErrorAction SilentlyContinue).Source }
if (-not $UvCommand) {
  if ($Offline) { throw "离线缓存中没有 uv：$CachedUv。请先在联网环境运行一次 setup-ai-os.ps1。" }
  $bootstrap = Join-Path $RuntimeCache "uv-install.ps1"
  Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $bootstrap -UseBasicParsing
  $env:UV_INSTALL_DIR = Split-Path -Parent $CachedUv
  $env:UV_NO_MODIFY_PATH = "1"
  & $bootstrap
  $UvCommand = $CachedUv
} elseif ($UvCommand -ne $CachedUv) { Copy-Item -LiteralPath $UvCommand -Destination $CachedUv -Force; $UvCommand = $CachedUv }

$previous = @{
  UV_CACHE_DIR = $env:UV_CACHE_DIR; UV_PYTHON_INSTALL_DIR = $env:UV_PYTHON_INSTALL_DIR
  UV_PYTHON_PREFERENCE = $env:UV_PYTHON_PREFERENCE; UV_OFFLINE = $env:UV_OFFLINE
}
try {
  $env:UV_CACHE_DIR = Join-Path $RuntimeCache "uv"
  $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeCache "python"
  $env:UV_PYTHON_PREFERENCE = "only-managed"
  if ($Offline) { $env:UV_OFFLINE = "1" }
  & $UvCommand venv $VenvRoot --python 3.12 --clear
  if ($LASTEXITCODE -ne 0) { throw "uv venv 退出码：$LASTEXITCODE" }
  & $UvCommand pip install --python $PythonCommand "qwenpaw==$($Lock.version)"
  if ($LASTEXITCODE -ne 0) { throw "uv pip install 退出码：$LASTEXITCODE" }
} finally {
  foreach ($name in $previous.Keys) { Set-Item -Path "env:$name" -Value $previous[$name] }
}
if (-not (Test-QwenPawRuntime)) { throw "项目运行环境安装后版本校验失败。" }
Write-Host "QwenPaw $($Lock.version) 项目运行环境安装完成：$RuntimeRoot"
