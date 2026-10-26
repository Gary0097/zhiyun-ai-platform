[CmdletBinding()]
param([string]$Workspace = (Join-Path $env:USERPROFILE '.qwenpaw'), [string]$SecretDir = (Join-Path $env:USERPROFILE '.qwenpaw.secret'), [switch]$LocalNoAuth)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) { throw '请先停止原平台服务，再接入已有数据；不会自动结束其他进程。' }
if (-not (Test-Path -LiteralPath (Join-Path $Workspace 'config.json')) -or -not (Test-Path -LiteralPath $SecretDir)) { throw '没有找到已有工作区或凭据目录，请明确指定原路径。' }
$Node = Join-Path $Root 'extras\node\node.exe'
if (-not (Test-Path -LiteralPath $Node)) { $Node = (Get-Command node -ErrorAction Stop).Source }
$Arguments = @((Join-Path $Root 'apps\zhizaoyunAIOS\scripts\local-instance.mjs'), '--workspace', $Workspace, '--secret-dir', $SecretDir)
if ($LocalNoAuth) { $Arguments += '--local-no-auth' }
& $Node @Arguments
if ($LASTEXITCODE -ne 0) { throw '接入失败，原工作区与模型数据未迁移。' }
