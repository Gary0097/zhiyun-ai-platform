$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'recovery.ps1')
function Check($Value, $Message) { if (-not $Value) { throw $Message } }
function Reject([scriptblock]$Action) { $failed = $false; try { & $Action } catch { $failed = $true }; Check $failed 'Expected rejection' }
$testRoot = Join-Path $env:TEMP ('aios-recovery-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    foreach ($relative in @('apps/zhizaoyunAIOS/qwenpaw.lock.json', 'apps/zhizaoyunAIOS/workspace/data.txt', 'apps/zhizaoyunAIOS/workspace.secret/key.txt', 'program.txt', 'hub.yaml')) {
        $file = Join-Path $testRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
        'original' | Set-Content -LiteralPath $file
    }
    $transaction = Join-Path $testRoot '.aios-updates/transaction-test'
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
    'user file' | Set-Content (Join-Path $testRoot 'unknown.txt')
    @('program.txt', 'new-runtime.txt', 'apps/zhizaoyunAIOS/workspace/data.txt') | Set-Content (Join-Path $testRoot '.aios-installed-files')
    Restore-UpdatePrograms $testRoot $transaction
    Check ((Get-Content (Join-Path $testRoot 'program.txt')) -eq 'original') 'Program rollback failed'
    Check ((Get-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace/data.txt')) -eq 'new user data') 'User data overwritten'
    Check ((Get-Content (Join-Path $testRoot 'apps/zhizaoyunAIOS/workspace.secret/key.txt')) -eq 'new credentials') 'Secrets overwritten'
    Check ((Get-Content (Join-Path $testRoot 'hub.yaml')) -eq 'new config') 'Hub settings overwritten'
    Check (Test-Path (Join-Path $testRoot 'unknown.txt')) 'Unknown file removed'
    Check ((Get-Content (Join-Path $testRoot 'user-notes.txt')) -eq 'changed user content') 'Unknown existing file overwritten'
    Check (-not (Test-Path (Join-Path $testRoot 'new-runtime.txt'))) 'New runtime file not removed'
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
    Write-Host 'Recovery tests passed: backup, rollback, data/secrets/config preservation, unknown files, traversal rejection, syntax'
} finally {
    # Fixed test prefix beneath TEMP only; no user installation paths can reach this cleanup.
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $prefix = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\aios-recovery-test-'
    if ($resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
