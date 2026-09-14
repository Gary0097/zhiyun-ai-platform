# Dot-sourceable recovery primitives. User data is never overwritten by rollback.
function Get-UpdatePath([string]$Root, [string]$Relative) {
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':') -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Unsafe update path' }
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Update path escapes installation' }
    for ($p = $full; $p; $p = Split-Path -Parent $p) {
        if (Test-Path -LiteralPath $p) {
            if ((Get-Item -Force -LiteralPath $p).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Update path contains a link' }
        }
    }
    return $full
}
function Test-UpdateData([string]$Relative) {
    $p = $Relative.Replace('\', '/').ToLowerInvariant()
    return $p -eq 'hub.yaml' -or $p -eq 'hub.runtime.yaml' -or $p.StartsWith('apps/zhizaoyunaios/workspace/') -or $p.StartsWith('apps/zhizaoyunaios/workspace.secret/') -or $p.StartsWith('.aios-updates/')
}
function Assert-UpdateStopped([string]$Root) {
    # No process is killed on the basis of a generic product name.
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $active = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -match 'start-ai-os|start-hub|setup-ai-os|setup-hub|qwenpaw')
    })
    if ($active.Count) { throw '安装目录仍有程序运行。请退出托盘、单机和 Hub 服务后重试。' }
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in 8088,8000 })
    if ($listeners.Count) { throw '8088 或 8000 仍在使用，已停止升级。请先停止对应服务。' }
}
function Stop-UpdateServices([string]$Root) {
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $owned = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    })
    foreach ($p in $owned) {
        # Re-read identity before stopping; refuse to kill another installation.
        $live = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ProcessId)" -ErrorAction Stop
        if ($live -and $live.CreationDate -eq $p.CreationDate -and $live.ExecutablePath -eq $p.ExecutablePath) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        }
    }
    Assert-UpdateStopped $Root
}
function New-UpdateSnapshot([string]$Root, [string]$Transaction, [scriptblock]$Pump = {}) {
    $Root = (Get-Item -Force -LiteralPath $Root).FullName
    $Transaction = (Get-Item -Force -LiteralPath $Transaction).FullName
    $snapshot = Join-Path $Transaction 'backup'
    $manifest = Get-UpdatePath $Root '.aios-installed-files'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw '安装文件清单缺失，无法保证安全恢复。请先修复安装。' }
    $programs = @((Get-Content -Encoding UTF8 -LiteralPath $manifest | Where-Object { $_ -and -not (Test-UpdateData $_) } | ForEach-Object { "$_" })) + @('.aios-installed-files')
    foreach ($relative in $programs) { $null = Get-UpdatePath $Root $relative }
    # Validate links before copying, including any links within user data.
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    $queue.Enqueue($Root)
    while ($queue.Count) {
        & $Pump
        foreach ($item in Get-ChildItem -Force -LiteralPath $queue.Dequeue()) {
            if ($item.FullName -eq (Join-Path $Root '.aios-updates')) { continue }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '安装含链接，无法保证完整备份，已停止升级。' }
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
        }
    }
    $copyArgs = @(('"' + $Root.TrimEnd('\') + '"'), ('"' + $snapshot + '"'), '/E', '/COPY:DAT', '/DCOPY:DAT', '/XJ', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/XD', ('"' + (Join-Path $Root '.aios-updates') + '"'))
    $copyInfo = New-Object Diagnostics.ProcessStartInfo
    $copyInfo.FileName = 'robocopy.exe'; $copyInfo.Arguments = $copyArgs -join ' '
    $copyInfo.UseShellExecute = $false; $copyInfo.CreateNoWindow = $true
    $copyInfo.RedirectStandardOutput = $true; $copyInfo.RedirectStandardError = $true
    $copy = [Diagnostics.Process]::Start($copyInfo)
    $copyOutput = $copy.StandardOutput.ReadToEndAsync(); $copyError = $copy.StandardError.ReadToEndAsync()
    while (-not $copy.WaitForExit(100)) { & $Pump }
    if ($copy.ExitCode -ge 8 -or $null -eq $copy.ExitCode) { throw '升级备份失败，程序未更新。请检查磁盘空间与文件权限。' }
    $snapshot = (Get-Item -Force -LiteralPath $snapshot).FullName
    $files = @(Get-ChildItem -File -Recurse -Force -LiteralPath $snapshot | ForEach-Object { $_.FullName.Substring($snapshot.Length + 1) })
    if (-not ($files -contains 'apps\zhizaoyunAIOS\qwenpaw.lock.json')) { throw '备份不完整，缺少版本锁。' }
    $programs = @($programs | Where-Object { Test-Path -LiteralPath (Join-Path $snapshot $_) -PathType Leaf })
    @{ root = $Root; files = $files; programs = $programs; status = 'backed-up' } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Transaction 'state.json')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'recovery.ps1') -Destination (Join-Path $Transaction 'recovery.ps1')
    @'
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'recovery.ps1')
$state = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'state.json') | ConvertFrom-Json
Assert-UpdateStopped $state.root
Restore-UpdatePrograms $state.root $PSScriptRoot
Write-Host 'Programs restored. User data was not overwritten. Review data migration recovery before restarting.'
'@ | Set-Content -Encoding UTF8 (Join-Path $Transaction 'restore.ps1')
}
function Restore-UpdatePrograms([string]$Root, [string]$Transaction) {
    $Root = (Get-Item -Force -LiteralPath $Root).FullName
    $state = Get-Content -Raw -LiteralPath (Join-Path $Transaction 'state.json') | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($state.root) -ne [IO.Path]::GetFullPath($Root)) { throw '备份不属于此安装。' }
    $snapshot = Join-Path $Transaction 'backup'
    if (-not $state.programs) { throw '备份缺少程序清单，拒绝覆盖未知文件。' }
    $restore = @($state.programs | Where-Object { -not (Test-UpdateData $_) })
    $added = @()
    $installed = Get-UpdatePath $Root '.aios-installed-files'
    if (Test-Path -LiteralPath $installed) {
        $added = @(Get-Content -Encoding UTF8 -LiteralPath $installed | Where-Object { $_ -and $_ -notin $state.files -and -not (Test-UpdateData $_) })
    }
    # Preflight every source/destination before any mutation.
    foreach ($relative in $restore) {
        $null = Get-UpdatePath $Root $relative
        $source = Get-UpdatePath $snapshot $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw '恢复备份缺少文件。' }
    }
    foreach ($relative in $added) { $null = Get-UpdatePath $Root $relative }
    foreach ($relative in $added) {
        $file = Get-UpdatePath $Root $relative
        if (Test-Path -LiteralPath $file -PathType Leaf) { Remove-Item -LiteralPath $file -Force }
    }
    foreach ($relative in $restore) {
        $file = Get-UpdatePath $Root $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
        Copy-Item -LiteralPath (Get-UpdatePath $snapshot $relative) -Destination $file -Force
    }
}
