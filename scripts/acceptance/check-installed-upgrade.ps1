# Manual acceptance for the existing disposable full-installer instance only.
# Default: read-only preflight. -ExecuteUpgrade explicitly starts the upgrade.
[CmdletBinding()]
param([switch]$ExecuteUpgrade)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
# Keep source ASCII for Windows PowerShell 5's default script decoding.
$testDirectoryName = (-join @([char]0x6574, [char]0x5305, [char]0x9A8C, [char]0x6536)) + ' 2.2.0'
$target = Join-Path 'C:\AI\zhiyun-ai-os-workspace' $testDirectoryName
$installer = Join-Path $repo 'dist\zhiyun-ai-os-v2.2.0-setup.exe'
$expectedHash = 'CD72E327195A81DD1B03600509129D682189F690B50EED376412405E7D413167'
$evidence = Join-Path $repo 'apps\zhizaoyunAIOS\runtime'
$accountState = Join-Path $evidence 'full-installer-account.json'
$workspace = Join-Path $target 'apps\zhizaoyunAIOS\workspace'
$auth = Join-Path $workspace 'secret\auth.json'
$hubConfig = Join-Path $target 'hub.yaml'
$sentinel = Join-Path $workspace 'acceptance-preserve.txt'
$unknown = Join-Path $target 'acceptance-user-file.txt'
$python = Join-Path $target 'apps\zhizaoyunAIOS\runtime\zhizaoyunAIOS\venv\Scripts\python.exe'

foreach ($path in @($installer, $accountState, $auth, $hubConfig, $python)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required acceptance file missing: $path" }
}
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Installer differs from the reviewed 037bdbc885 candidate; re-review before execution.'
}
$registered = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ZhizaoyunAIOS'
if ([IO.Path]::GetFullPath($registered.InstallLocation).TrimEnd('\') -ne $target) {
    throw 'Registered installation is not the disposable full-installer instance.'
}
foreach ($path in @($target, $workspace, (Split-Path $auth), $sentinel, $unknown)) {
    if ((Test-Path -LiteralPath $path) -and
        ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Acceptance path must not be a link: $path"
    }
}
Write-Output "Reviewed installer SHA256: $expectedHash"
Write-Output "Upgrade target: $target"
Write-Output 'Will retain and hash-check auth.json, hub.yaml, a workspace marker and an unknown root file.'
if (-not $ExecuteUpgrade) {
    Write-Output 'READ-ONLY PREFLIGHT PASSED. No installation or file writes performed.'
    return
}

# Do not overwrite an existing marker, even if left by a prior manual attempt.
foreach ($path in @($sentinel, $unknown)) {
    if (-not (Test-Path -LiteralPath $path)) {
        [IO.File]::WriteAllText($path, 'AIOS 2.2.0 disposable upgrade retention evidence')
    }
}
$before = @(@($auth, $hubConfig, $sentinel, $unknown) | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_ -Algorithm SHA256
    [pscustomobject]@{ Path = $hash.Path; Hash = $hash.Hash }
})
$before | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'upgrade-before.json') -Encoding UTF8
$process = Start-Process -FilePath $installer -ArgumentList @('--dir', ('"' + $target + '"')) -WindowStyle Hidden -PassThru
$null = $process.Handle
Write-Output "Upgrade process ID: $($process.Id)"
$timer = [Diagnostics.Stopwatch]::StartNew()
while (-not $process.HasExited) {
    if ($timer.Elapsed.TotalMinutes -ge 30) {
        throw "Observation window ended; process $($process.Id) may still be running. Inspect it before any retry."
    }
    Start-Sleep -Seconds 5
    $process.Refresh()
}
Write-Output "Upgrade exit code: $($process.ExitCode)"
if ($process.ExitCode -ne 0) { throw 'Upgrade failed. Inspect install-log.txt; do not report acceptance passed.' }
foreach ($item in $before) {
    if ((Get-FileHash -LiteralPath $item.Path -Algorithm SHA256).Hash -ne $item.Hash) {
        throw "Preserved file changed: $($item.Path)"
    }
}
Write-Output 'PASS all four preserved file hashes unchanged'
& $python (Join-Path $PSScriptRoot 'probe-auth.py') --url http://127.0.0.1:8088 --state $accountState
if ($LASTEXITCODE -ne 0) { throw 'Existing account authentication failed after upgrade.' }
Write-Output 'PASS full installer upgrade and existing account authentication'
