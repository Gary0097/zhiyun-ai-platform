$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
. (Join-Path $PSScriptRoot 'recovery.ps1')
function Check($Value, $Message) { if (-not $Value) { throw $Message } }
function Reject([scriptblock]$Action) { $failed = $false; try { & $Action } catch { $failed = $true }; Check $failed 'Expected rejection' }
$testRoot = Join-Path $env:TEMP ('aios-recovery-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    foreach ($relative in @('apps/zhizaoyunAIOS/qwenpaw.lock.json', 'apps/zhizaoyunAIOS/workspace/data.txt', 'apps/zhizaoyunAIOS/workspace.secret/key.txt', 'program.txt', 'hub.yaml', 'docs/custom.txt', 'apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv/old-extra.py')) {
        $file = Join-Path $testRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
        'original' | Set-Content -LiteralPath $file
    }
    $transaction = Join-Path $testRoot ('.aios-updates/transaction-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $transaction | Out-Null
    @('program.txt', 'apps/zhizaoyunAIOS/qwenpaw.lock.json') | Set-Content (Join-Path $testRoot '.aios-installed-files')
    'old user content' | Set-Content (Join-Path $testRoot 'user-notes.txt')
    New-UpdateSnapshot $testRoot $transaction
    'changed user content' | Set-Content (Join-Path $testRoot 'user-notes.txt')
    'new program' | Set-Content (Join-Path $testRoot 'program.txt')
    'new user data' | Set-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace/data.txt')
    'new credentials' | Set-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace.secret/key.txt')
    'new config' | Set-Content (Join-Path $testRoot 'hub.yaml')
    'new runtime' | Set-Content (Join-Path $testRoot 'new-runtime.txt')
    'overwritten by new package' | Set-Content (Join-Path $testRoot 'docs/custom.txt')
    'user file' | Set-Content (Join-Path $testRoot 'unknown.txt')
    @('program.txt', 'new-runtime.txt', 'apps/zhizaoyunAIOS/workspace/data.txt', 'DOCS/custom.txt') | Set-Content (Join-Path $testRoot '.aios-installed-files')
    Restore-UpdatePrograms $testRoot $transaction
    Check ((Get-Content (Join-Path $testRoot 'program.txt')) -eq 'original') 'Program rollback failed'
    Check ((Get-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace/data.txt')) -eq 'new user data') 'User data overwritten'
    Check ((Get-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace.secret/key.txt')) -eq 'new credentials') 'Secrets overwritten'
    Check ((Get-Content (Join-Path $testRoot 'hub.yaml')) -eq 'new config') 'Hub settings overwritten'
    Check (Test-Path (Join-Path $testRoot 'unknown.txt')) 'Unknown file removed'
    Check ((Get-Content (Join-Path $testRoot 'user-notes.txt')) -eq 'changed user content') 'Unknown existing file overwritten'
    Check ((Get-Content (Join-Path $testRoot 'docs/custom.txt')) -eq 'original') 'Mixed separators or casing lost pre-existing user file claimed by new package'
    Check (-not (Test-Path (Join-Path $testRoot 'new-runtime.txt'))) 'New runtime file not removed'
    Check (Test-Path (Join-Path $transaction 'quarantine/new-runtime.txt')) 'New runtime file was not kept recoverably'

    # Real installer failure paths: no success manifest is written in either case.
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    $probe = Join-Path $transaction 'installer-probe.exe'
    $version = Join-Path $transaction 'VersionInfo.cs'
    'static class VersionInfo { public const string AppVersion = "2.2.0"; }' | Set-Content $version
    & $compiler /nologo /target:exe /main:InstallerFailureProbe "/out:$probe" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll (Join-Path $PSScriptRoot 'installer-failure-probe.cs') (Join-Path $PSScriptRoot '../exe-installer/bootstrap.cs') (Join-Path $PSScriptRoot '../exe-installer/wizard.cs') (Join-Path $PSScriptRoot '../exe-installer/uninstaller.cs') $version
    Check ($LASTEXITCODE -eq 0) 'Installer failure probe compilation failed'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Add-Type -AssemblyName System.IO.Compression
    $zipPath = Join-Path $transaction 'partial.zip'
    $zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
    foreach ($name in @('scripts/partial-module.mjs', 'blocked')) {
        $writer = New-Object IO.StreamWriter($zip.CreateEntry($name).Open())
        $writer.Write('partial new version'); $writer.Dispose()
    }
    $zip.Dispose()
    New-Item -ItemType Directory -Path (Join-Path $testRoot 'blocked') | Out-Null
    $previousTransaction = $env:AIOS_UPDATE_TRANSACTION
    try {
        $env:AIOS_UPDATE_TRANSACTION = (Get-Item -LiteralPath $transaction).FullName
        $oldManifest = Get-Content -Raw (Join-Path $testRoot '.aios-installed-files')
        & $probe extract $testRoot $zipPath
        Check ($LASTEXITCODE -eq 17) 'Expected late extraction failure'
        Check (Test-Path (Join-Path $testRoot 'scripts/partial-module.mjs')) 'Failure did not occur after first extraction write'
        Check ((Get-Content -Raw (Join-Path $testRoot '.aios-installed-files')) -eq $oldManifest) 'Partial extraction unexpectedly committed uninstall manifest'
        Restore-UpdatePrograms $testRoot $transaction
        Check (-not (Test-Path (Join-Path $testRoot 'scripts/partial-module.mjs'))) 'Partial extracted module survived recovery'
        Check (Test-Path (Join-Path $transaction 'quarantine/scripts/partial-module.mjs')) 'Partial extracted module not quarantined'
        @'
param([switch]$Offline, [string]$CacheDir)
$venv = Join-Path $PSScriptRoot 'apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv'
Remove-Item -LiteralPath (Join-Path $venv 'old-extra.py')
'partial python package' | Set-Content -LiteralPath (Join-Path $venv 'partial-new.py')
exit 7
'@ | Set-Content -Encoding UTF8 (Join-Path $testRoot 'setup-ai-os.ps1')
        & $probe runtime $testRoot
        Check ($LASTEXITCODE -eq 7) 'Expected partial runtime setup failure'
        Check ((Get-Content -Raw (Join-Path $testRoot '.aios-installed-files')) -eq $oldManifest) 'Failed setup unexpectedly committed uninstall manifest'
        Restore-UpdatePrograms $testRoot $transaction
        Check (-not (Test-Path (Join-Path $testRoot 'apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv/partial-new.py'))) 'Partial Python package survived recovery'
        Check ((Get-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv/old-extra.py')) -eq 'original') 'Pre-existing untracked runtime package lost during failed setup'
        Restore-UpdatePrograms $testRoot $transaction
    } finally { $env:AIOS_UPDATE_TRANSACTION = $previousTransaction }

    # The generated standalone entry must reject a concurrent updater/recovery before preflight.
    $guard = New-Object Threading.Mutex($false, 'Local\ZhizaoyunAIOS.Update')
    $held = $guard.WaitOne(0)
    Check $held 'Test could not acquire update mutex'
    try {
        $psi = New-Object Diagnostics.ProcessStartInfo
        $psi.FileName = 'powershell.exe'; $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $transaction 'restore.ps1') + '"'
        $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
        $psi.RedirectStandardError = $true; $psi.RedirectStandardOutput = $true
        $child = [Diagnostics.Process]::Start($psi)
        $err = $child.StandardError.ReadToEndAsync(); $out = $child.StandardOutput.ReadToEndAsync()
        Check ($child.WaitForExit(30000)) 'Concurrent recovery did not exit'
        Check ($child.ExitCode -ne 0 -and $err.Result.Contains('Another update or recovery is running.')) 'Standalone recovery bypassed update mutex'
    } finally { if ($held) { $guard.ReleaseMutex() }; $guard.Dispose() }
    Reject { Get-UpdatePath $testRoot '../escape.txt' }
    Reject { Get-UpdatePath $testRoot 'C:/outside.txt' }
    Reject { Get-UpdatePath $testRoot 'program.txt:stream' }
    '../../escape.txt' | Set-Content (Join-Path $testRoot '.aios-installed-files')
    Reject { Restore-UpdatePrograms $testRoot $transaction }
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '../../update-ai-os.ps1'), [ref]$tokens, [ref]$errors)
    Check (-not $errors.Count) 'Updater PowerShell syntax failure'
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    $launcher = Join-Path $testRoot 'launcher-test.exe'
    & $compiler /nologo /target:exe /main:Launcher "/out:$launcher" /r:System.Windows.Forms.dll /r:System.Drawing.dll (Join-Path $PSScriptRoot '../exe-installer/launcher.cs')
    Check ($LASTEXITCODE -eq 0) 'Launcher compilation failed'
    & $launcher --selftest
    Check ($LASTEXITCODE -eq 0) 'Launcher selftest failed'
    # Exercise the actual unattended entry, ACL creation, mutex and child-process plumbing.
    # A clearly isolated metadata stub prevents network access; this is not upgrade acceptance.
    $helperDir = Join-Path $testRoot 'scripts/updates'
    New-Item -ItemType Directory -Force -Path $helperDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'recovery.ps1') -Destination $helperDir
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../../update-ai-os.ps1') -Destination $testRoot
    'console.log(JSON.stringify({available:false,current:"unit-test-only"}))' | Set-Content -Encoding UTF8 (Join-Path $helperDir 'client.mjs')
    $checked = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $testRoot 'update-ai-os.ps1') -CheckOnly
    Check ($LASTEXITCODE -eq 0) 'Unattended check entry failed'
    Check (($checked | ConvertFrom-Json).current -eq 'unit-test-only') 'Check output lost'
    $cacheAcl = Get-Acl -LiteralPath (Join-Path $testRoot '.aios-updates')
    Check $cacheAcl.AreAccessRulesProtected 'Backup directory inherited broad permissions'
    Write-Host 'Recovery tests passed: backup, normalized paths, partial extraction/setup recovery, quarantine, mutex exclusion, data/secrets/config preservation, unknown files, traversal rejection, entry and syntax'
} finally {
    # Fixed test prefix beneath TEMP only; no user installation paths can reach this cleanup.
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $prefix = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\aios-recovery-test-'
    if ($resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
