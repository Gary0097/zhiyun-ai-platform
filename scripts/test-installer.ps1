param([string]$OutputDir = "")
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot 'apps/zhizaoyunAIOS/runtime/installer-tests' }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$Compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$SourceDir = Join-Path $PSScriptRoot 'exe-installer'
$VersionSource = Join-Path $OutputDir 'VersionInfo.cs'
$AppVersion = (Get-Content (Join-Path $RepoRoot 'apps/zhizaoyunAIOS/qwenpaw.lock.json') -Raw | ConvertFrom-Json).version
[IO.File]::WriteAllText($VersionSource, ('static class VersionInfo { public const string AppVersion = "' + $AppVersion + '"; }'))
$TestExe = Join-Path $OutputDir 'installer-tests.exe'
& $Compiler /nologo /target:exe /main:InstallerTests "/out:$TestExe" "/win32manifest:$SourceDir\installer.manifest" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll "$SourceDir\bootstrap.cs" "$SourceDir\wizard.cs" "$SourceDir\uninstaller.cs" "$SourceDir\tests.cs" $VersionSource
if ($LASTEXITCODE -ne 0) { throw 'Installer test compilation failed' }
& $TestExe $OutputDir
if ($LASTEXITCODE -ne 0) { throw 'Installer tests failed' }
