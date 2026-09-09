[CmdletBinding()]
param([switch]$NoElevation)
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
  if ($NoElevation) { throw 'Windows Hub Local runtimes require administrator privileges (AppContainer). Run start-hub.cmd as administrator.' }
  Write-Host 'Hub requires administrator permission for isolated user runtimes. Please approve the Windows prompt.'
  try {
    $Elevated = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), '-NoElevation') -PassThru -Wait
    exit $Elevated.ExitCode
  } catch { throw 'Hub was not started because administrator permission was not granted.' }
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
if ($LASTEXITCODE -ne 0) { throw "Hub setup failed ($LASTEXITCODE)." }
& node (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\hub-config.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Hub configuration failed.' }
$HubBin = Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts'
$HubHost = & (Join-Path $HubBin 'python.exe') (Join-Path $ProjectRoot 'apps\zhizaoyunAIOS\scripts\hub-bind-host.py')
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Hub administrator state; no server was started.' }
if ($HubHost -eq '127.0.0.1') { Write-Host 'First-time setup: register the administrator at http://127.0.0.1:8000, then restart Hub for team access.' }
& (Join-Path $HubBin 'qwenpaw.exe') hub --host $HubHost --port 8000 --force-public --config (Join-Path $ProjectRoot 'hub.runtime.yaml')
exit $LASTEXITCODE
