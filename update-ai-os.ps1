[CmdletBinding()]
param([switch]$CheckOnly, [string]$Recover = '')
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
. (Join-Path $Root 'scripts/updates/recovery.ps1')
Add-Type -AssemblyName System.Windows.Forms
$mutex = New-Object Threading.Mutex($false, 'Local\ZhizaoyunAIOS.Update')
$locked = $false
$transaction = $null
$progressForm = $null
function Show-UpdateStatus([string]$Text) {
    if ($CheckOnly) { return }
    if (-not $script:progressForm) {
        $script:progressForm = New-Object Windows.Forms.Form
        $script:progressForm.Text = '智造云 AIOS 更新'
        $script:progressForm.Width = 460; $script:progressForm.Height = 150
        $script:progressForm.StartPosition = 'CenterScreen'
        $script:progressForm.ControlBox = $false
        $script:progressLabel = New-Object Windows.Forms.Label
        $script:progressLabel.Dock = 'Fill'
        $script:progressLabel.Padding = New-Object Windows.Forms.Padding(16)
        $script:progressForm.Controls.Add($script:progressLabel)
        $bar = New-Object Windows.Forms.ProgressBar
        $bar.Dock = 'Bottom'; $bar.Style = 'Marquee'
        $script:progressForm.Controls.Add($bar)
        $script:progressForm.Show()
    }
    $script:progressLabel.Text = $Text
    [Windows.Forms.Application]::DoEvents()
}
function Invoke-UpdateClient([string]$Action) {
    $node = Join-Path $Root 'extras/node/node.exe'
    if (-not (Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $node
    $psi.Arguments = '"' + (Join-Path $Root 'scripts/updates/client.mjs') + '" ' + $Action
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $child = [Diagnostics.Process]::Start($psi)
    $stdout = $child.StandardOutput.ReadToEndAsync(); $stderr = $child.StandardError.ReadToEndAsync()
    while (-not $child.WaitForExit(100)) { [Windows.Forms.Application]::DoEvents() }
    if ($child.ExitCode -ne 0) { throw $stderr.Result }
    return ($stdout.Result | ConvertFrom-Json)
}
try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { throw '另一个更新任务正在运行。' }
    if (Test-Path -LiteralPath (Join-Path $Root '.git')) { throw '源码工作目录请通过 PR 升级；在线安装器仅用于已安装的软件。' }
    $cache = Get-UpdatePath $Root '.aios-updates'
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    # Backups include secrets: restrict inheritance before writing any backup.
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $cache -AclObject $acl
    if ($Recover) {
        if ($Recover -notmatch '^transaction-[a-f0-9]{32}$') { throw '恢复编号无效。' }
        $transaction = Get-UpdatePath $Root ".aios-updates/$Recover"
        Assert-UpdateStopped $Root
        Restore-UpdatePrograms $Root $transaction
        [Windows.Forms.MessageBox]::Show('旧程序已恢复。用户数据未覆盖；若新版做过数据迁移，请按备份恢复说明核对后再启动。', '智造云 AIOS') | Out-Null
        exit 0
    }
    Show-UpdateStatus '正在检查经过审核的智造云正式版本…'
    $info = Invoke-UpdateClient 'check'
    if ($CheckOnly) { $info | ConvertTo-Json; exit 0 }
    if (-not $info.available) { [Windows.Forms.MessageBox]::Show($info.message, '智造云 AIOS') | Out-Null; exit 0 }
    $answer = [Windows.Forms.MessageBox]::Show("发现智造云 AIOS $($info.version)，当前 $($info.current)。`n将下载更新、停止本安装服务、完整备份后覆盖安装。请先保存工作。`n更新包约 $([math]::Ceiling($info.size / 1MB)) MB；备份需要额外磁盘空间。`n是否继续？", '智造云 AIOS 更新', 'YesNo', 'Question')
    if ($answer -ne 'Yes') { exit 0 }
    Show-UpdateStatus '正在下载并校验更新包，请稍候…'
    $package = Invoke-UpdateClient 'download'
    if (-not $package.available -or $package.version -ne $info.version) { throw '更新版本已变化，请重新检查。' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $package.path).Hash.ToLowerInvariant() -ne $package.sha256) { throw '安装前校验失败。' }
    Show-UpdateStatus '正在停止本安装服务，准备完整备份…'
    Stop-UpdateServices $Root
    $transaction = Join-Path $cache ('transaction-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $transaction | Out-Null
    Show-UpdateStatus '正在备份程序、工作区和账号数据，请勿关闭电脑…'
    New-UpdateSnapshot $Root $transaction { [Windows.Forms.Application]::DoEvents() }
    # This process has loaded all recovery functions before the installer can replace scripts.
    Assert-UpdateStopped $Root
    Show-UpdateStatus '正在安装更新并等待服务启动，首次准备可能需要数分钟…'
    $installInfo = New-Object Diagnostics.ProcessStartInfo
    $installInfo.FileName = $package.path; $installInfo.Arguments = '--dir "' + $Root.TrimEnd('\') + '"'
    $installInfo.UseShellExecute = $false; $installInfo.CreateNoWindow = $true
    $installer = [Diagnostics.Process]::Start($installInfo)
    while (-not $installer.WaitForExit(100)) { [Windows.Forms.Application]::DoEvents() }
    if ($installer.ExitCode -ne 0) { throw "安装器失败（$($installer.ExitCode)），请使用保留的备份恢复。" }
    $actual = (Get-Content -Raw (Join-Path $Root 'apps/zhizaoyunAIOS/qwenpaw.lock.json') | ConvertFrom-Json).version
    if ($actual -ne $package.version) { throw '安装后版本锁不一致。' }
    $runtime = Join-Path $Root 'apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv/Scripts/qwenpaw.exe'
    $runtimeVersion = & $runtime --version 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $runtimeVersion -notmatch ('version\s+' + [regex]::Escape($package.version) + '\s*$')) { throw '安装后实际运行时版本校验失败。' }
    [Windows.Forms.MessageBox]::Show("更新到 $actual 完成。`n备份保留于 $transaction。`nHub 请按原入口重新启动。", '智造云 AIOS') | Out-Null
} catch {
    $message = $_.Exception.Message
    if ($transaction -and (Test-Path -LiteralPath (Join-Path $transaction 'state.json'))) {
        # Do not automatically restore databases after a newer runtime may have migrated them.
        $message += "`n完整备份：$transaction`n停止所有服务后，用 PowerShell 运行备份目录内的 restore.ps1 恢复程序。数据恢复请参照在线更新说明。"
    }
    if ($CheckOnly) { Write-Error $message } else { [Windows.Forms.MessageBox]::Show($message, '更新未完成', 'OK', 'Error') | Out-Null }
    exit 1
} finally {
    if ($progressForm) { $progressForm.Dispose() }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
