# Document text extraction via local Office COM (Word/Excel/PowerPoint) or plain unzip.
# Invoked by server/documents.js: powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Sta -File extract-doc.ps1 -Path <file> -OutFile <txt> -Kind <word|excel|ppt|pdf|unzip>
# - Kind word/pdf: Word reads content (Word can open PDFs and extract text).
# - Kind excel:   iterate used-range cells, rows joined by tabs.
# - Kind ppt:     slide text frames and tables.
# - Kind unzip:   Expand-Archive <Path> into <OutFile> directory (OOXML fallback).
# Output is written to OutFile as UTF-8 (no BOM); the script itself stays ASCII so
# Windows PowerShell 5.1 does not misread it.
param(
  [Parameter(Mandatory = $true)][string]$Path,
  [Parameter(Mandatory = $true)][string]$OutFile,
  [Parameter(Mandatory = $true)][ValidateSet('word', 'excel', 'ppt', 'pdf', 'unzip')][string]$Kind
)
$ErrorActionPreference = 'Stop'
$sb = New-Object System.Text.StringBuilder

function Quit-ComObject($app) {
  try { $app.Quit() } catch { }
  try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null } catch { }
}

function Flush-Output {
  [System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
}

try {
  if ($Kind -eq 'unzip') {
    if (Test-Path $OutFile) { Remove-Item -Recurse -Force $OutFile }
    Expand-Archive -LiteralPath $Path -DestinationPath $OutFile -Force
    exit 0
  }

  if ($Kind -eq 'word' -or $Kind -eq 'pdf') {
    $w = New-Object -ComObject Word.Application
    $w.Visible = $false
    $w.DisplayAlerts = 0
    try {
      $w.Options.ConfirmConversions = $false
      $d = $w.Documents.Open($Path, $false, $true)
      try { [void]$sb.AppendLine($d.Content.Text) } finally { $d.Close(0) }
    } finally { Quit-ComObject $w }
  }
  elseif ($Kind -eq 'excel') {
    $x = New-Object -ComObject Excel.Application
    $x.Visible = $false
    $x.DisplayAlerts = $false
    try {
      $wb = $x.Workbooks.Open($Path, 0, $true)
      try {
        foreach ($ws in $wb.Worksheets) {
          [void]$sb.AppendLine("=== Sheet: $($ws.Name) ===")
          $used = $ws.UsedRange
          $rows = [Math]::Min($used.Rows.Count, 3000)
          $cols = [Math]::Min($used.Columns.Count, 200)
          for ($r = 1; $r -le $rows; $r++) {
            $cells = @()
            for ($c = 1; $c -le $cols; $c++) {
              $v = $null
              try { $v = $used.Cells.Item($r, $c).Text } catch { $v = $null }
              if ($null -ne $v) { $cells += [string]$v }
            }
            $line = ($cells -join "`t").TrimEnd()
            if ($line -ne '') { [void]$sb.AppendLine($line) }
          }
        }
      } finally { $wb.Close($false) }
    } finally { Quit-ComObject $x }
  }
  elseif ($Kind -eq 'ppt') {
    $p = New-Object -ComObject PowerPoint.Application
    try {
      $pres = $p.Presentations.Open($Path, $true, $false, $false)
      try {
        foreach ($slide in $pres.Slides) {
          [void]$sb.AppendLine("=== Slide $($slide.SlideIndex) ===")
          foreach ($shape in $slide.Shapes) {
            try {
              if ($shape.HasTextFrame) {
                if ($shape.TextFrame.HasText) { [void]$sb.AppendLine($shape.TextFrame.TextRange.Text) }
              }
            } catch { }
            try {
              if ($shape.HasTable) {
                $tbl = $shape.Table
                for ($r = 1; $r -le $tbl.Rows.Count; $r++) {
                  $cells = @()
                  for ($c = 1; $c -le $tbl.Columns.Count; $c++) {
                    try { $cells += [string]$tbl.Cell($r, $c).Shape.TextFrame.TextRange.Text } catch { $cells += '' }
                  }
                  [void]$sb.AppendLine(($cells -join "`t"))
                }
              }
            } catch { }
          }
        }
      } finally { $pres.Close() }
    } finally { Quit-ComObject $p }
  }

  Flush-Output
  exit 0
} catch {
  try { Flush-Output } catch { }
  Write-Error $_.Exception.Message
  exit 1
}
