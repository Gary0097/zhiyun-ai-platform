param([Parameter(Mandatory=$true)][string]$Archive, [Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
$Repository = Split-Path -Parent $PSScriptRoot
$Archive = (Resolve-Path -LiteralPath $Archive).Path
$Target = [IO.Path]::GetFullPath($Target)
if (Test-Path -LiteralPath $Target) { throw 'Use a new empty acceptance target; existing installations must never be overwritten by this test.' }
$Build = Join-Path $Repository 'apps\zhizaoyunAIOS\runtime\office-installer-test'
New-Item -ItemType Directory -Force -Path $Build | Out-Null
$Source = @'
using System;
using System.IO;
class OfficeInstallerAcceptance {
  static int Main(string[] args) {
    try {
      int count = Installer.ExtractTo(args[0], args[1], null);
      Console.WriteLine("Extracted " + count + " installer files");
      int code = Installer.RunRuntimeSetup(args[1], Path.Combine(args[1], "office-install-test.log"));
      if (code != 0) throw new Exception("Offline setup failed: " + code);
      Console.WriteLine("PASS actual installer extraction + offline runtime and office setup");
      return 0;
    } catch (Exception e) { Console.Error.WriteLine(e); return 1; }
  }
}
'@
[IO.File]::WriteAllText((Join-Path $Build 'acceptance.cs'), $Source)
[IO.File]::WriteAllText((Join-Path $Build 'VersionInfo.cs'), 'static class VersionInfo { public const string AppVersion = "2.2.1"; }')
$Compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$SourceDir = Join-Path $PSScriptRoot 'exe-installer'
$Exe = Join-Path $Build 'office-installer-test.exe'
& $Compiler /nologo /target:exe /main:OfficeInstallerAcceptance "/out:$Exe" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll "$SourceDir\bootstrap.cs" "$SourceDir\wizard.cs" "$SourceDir\uninstaller.cs" "$Build\VersionInfo.cs" "$Build\acceptance.cs"
if ($LASTEXITCODE -ne 0) { throw 'Acceptance harness compilation failed' }
$previous = @{ UV_OFFLINE=$env:UV_OFFLINE; HTTP_PROXY=$env:HTTP_PROXY; HTTPS_PROXY=$env:HTTPS_PROXY; ALL_PROXY=$env:ALL_PROXY }
try {
  $env:UV_OFFLINE='1'
  $env:HTTP_PROXY='http://127.0.0.1:9'
  $env:HTTPS_PROXY='http://127.0.0.1:9'
  $env:ALL_PROXY='http://127.0.0.1:9'
  & $Exe $Archive $Target
  if ($LASTEXITCODE -ne 0) { throw ('Offline installer acceptance failed. Inspect ' + (Join-Path $Target 'office-install-test.log')) }
  $Node = Join-Path $Target 'extras\node\node.exe'
  $Setup = Join-Path $Target 'apps\zhizaoyunAIOS\scripts\setup-office.mjs'
  $Repeat = & $Node $Setup --offline 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0 -or $Repeat -notmatch 'no dependency probe, download or LibreOffice process') { throw 'Repeated office setup did not use its receipt fast path' }
  Write-Output 'PASS repeat setup: no dependency probe, download or LibreOffice process'
  $RuntimePython = Join-Path $Target 'apps\zhizaoyunAIOS\runtime\zhizaoyunAIOS\venv\Scripts\python.exe'
  $env:SOFFICE = Join-Path $Target 'extras\libreoffice\program\soffice.com'
  $env:PYTHONUTF8='1'
  & $RuntimePython (Join-Path $Target 'scripts\test-office-capabilities.py') --output (Join-Path $Target 'office-acceptance-fixtures')
  if ($LASTEXITCODE -ne 0) { throw 'Installed office functionality failed' }
  Write-Output 'PASS fresh offline install: document/OCR/conversion/Excel recalculation'
} finally {
  foreach ($name in $previous.Keys) { Set-Item -Path "env:$name" -Value $previous[$name] }
}
