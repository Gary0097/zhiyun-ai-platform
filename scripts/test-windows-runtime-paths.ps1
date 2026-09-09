$ErrorActionPreference = 'Stop'
$Repository = Split-Path -Parent $PSScriptRoot
$ProbeFile = Join-Path $Repository 'setup-ai-os.ps1'
$ParsedTokens = $null
$ParsedErrors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($ProbeFile, [ref]$ParsedTokens, [ref]$ParsedErrors)
if ($ParsedErrors.Count) { throw 'Setup script parse failed' }
$Function = $Ast.Find({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -eq 'Test-QwenPawRuntime' }, $true)
if (-not $Function) { throw 'Runtime probe missing' }
Invoke-Expression $Function.Extent.Text
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ('aios-runtime-path-' + [guid]::NewGuid().ToString('N'))
try {
    $VenvRoot = Join-Path $TestRoot '中文 workspace'
    $ManagedPython = Join-Path $TestRoot '基础 Python'
    New-Item -ItemType Directory -Path $VenvRoot,$ManagedPython | Out-Null
    [IO.File]::WriteAllText((Join-Path $ManagedPython 'python.exe'), '')
    $PythonCommand = (Get-Command python.exe -ErrorAction Stop).Source
    $QwenPawCommand = Join-Path $VenvRoot 'qwenpaw.cmd'
    [IO.File]::WriteAllText($QwenPawCommand, "@echo off`r`necho QwenPaw, version 2.2.0`r`n")
    $Lock = [pscustomobject]@{ version = '2.2.0' }
    $Configuration = Join-Path $VenvRoot 'pyvenv.cfg'
    [IO.File]::WriteAllText($Configuration, ('home = ' + $ManagedPython + "`n"), (New-Object Text.UTF8Encoding($false)))
    if (-not (Test-QwenPawRuntime)) { throw 'UTF-8 managed Python path rejected' }
    Write-Output 'PASS Windows PowerShell runtime probe accepts UTF-8 Chinese paths with spaces'
    [IO.File]::WriteAllText($Configuration, ('home = ' + (Join-Path $TestRoot 'missing') + "`n"), (New-Object Text.UTF8Encoding($false)))
    if (Test-QwenPawRuntime) { throw 'Missing Python home incorrectly accepted' }
    Write-Output 'PASS missing managed Python home remains rejected'
} finally {
    $ResolvedTestRoot = [IO.Path]::GetFullPath($TestRoot)
    $AllowedPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\aios-runtime-path-'
    if (-not $ResolvedTestRoot.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected cleanup path' }
    if (Test-Path -LiteralPath $ResolvedTestRoot) { Remove-Item -LiteralPath $ResolvedTestRoot -Recurse -Force }
}
