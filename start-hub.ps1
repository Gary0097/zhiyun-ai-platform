[CmdletBinding()]
param([switch]$NoElevation)
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
  if ($NoElevation) { throw 'Windows Hub 用户隔离环境需要管理员权限（AppContainer），请以管理员身份运行 start-hub.cmd。' }
  Write-Host 'Hub 用户隔离环境需要管理员权限，请允许 Windows 授权提示。'
  try {
    $Elevated = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), '-NoElevation') -PassThru -Wait
    exit $Elevated.ExitCode
  } catch { throw '未获得管理员权限，Hub 尚未启动。' }
}
Set-Location -LiteralPath $ProjectRoot
$PortableNode = Join-Path $ProjectRoot 'extras\node'
if (Test-Path -LiteralPath (Join-Path $PortableNode 'node.exe')) { $env:PATH = $PortableNode + ';' + $env:PATH }
$env:PYTHONIOENCODING = 'utf-8'
$env:QWENPAW_WORKING_DIR = Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\workspace'
$Cache = Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\runtime\cache'
$SetupArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $ProjectRoot 'setup-hub.ps1'), '-CacheDir', $Cache)
if (Test-Path -LiteralPath (Join-Path $Cache 'OFFLINE-PACKAGE')) { $SetupArgs += '-Offline' }
& powershell.exe @SetupArgs
if ($LASTEXITCODE -ne 0) { throw "Hub 环境配置失败（$LASTEXITCODE）。" }
& node (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\hub-config.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Hub 配置失败。' }
& node (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\chinese-defaults.mjs')
if ($LASTEXITCODE -ne 0) { throw '中文默认配置设置失败。' }
# 办公专属默认技能包预置（aios-office 分支）：与单机模式共用同一工作区；
# 预置失败仅告警，不阻断 Hub 启动（QWENPAW_WORKING_DIR 已在上方设置）
& node (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\provision-office-skills.mjs')
if ($LASTEXITCODE -ne 0) { Write-Host '[WARN] 办公技能包预置失败（不影响 Hub 启动）。' }
$HubBin = Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts'
if (Test-Path -LiteralPath (Join-Path $HubBin 'soffice.exe')) {
  $env:SOFFICE = Join-Path $HubBin 'soffice.exe'
  $env:PATH = $HubBin + ';' + $env:PATH
}
$HubHost = & (Join-Path $HubBin 'python.exe') (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\hub-bind-host.py')
if ($LASTEXITCODE -ne 0) { throw '无法读取 Hub 管理员状态，服务尚未启动。' }
if ($HubHost -eq '127.0.0.1') { Write-Host '首次配置：请访问 http://127.0.0.1:8000 注册管理员，然后重启 Hub 开放团队访问。' }
& (Join-Path $HubBin 'qwenpaw.exe') hub --host $HubHost --port 8000 --force-public --config (Join-Path $ProjectRoot 'hub.runtime.yaml')
exit $LASTEXITCODE
