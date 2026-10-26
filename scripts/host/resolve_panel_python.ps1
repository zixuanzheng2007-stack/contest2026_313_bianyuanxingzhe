# Pick a Python that can "import serial". Explorer PATH often differs from terminal PATH.
param(
  [switch]$InstallIfMissing
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-IsWindowsAppsStub {
  param([string]$Exe)
  return ($Exe -match '[\\/]WindowsApps[\\/]python\.exe$' -or $Exe -match '[\\/]Microsoft[\\/]WindowsApps[\\/]python\.exe$')
}

function Test-PythonHasPyserial {
  param([string]$Exe)
  if (-not $Exe -or $Exe -notmatch '\.exe$') { return $false }
  if (Test-IsWindowsAppsStub $Exe) { return $false }
  if (-not (Test-Path -LiteralPath $Exe)) { return $false }
  & cmd.exe /c "`"$Exe`" -c `"import serial`" >nul 2>nul"
  return ($LASTEXITCODE -eq 0)
}

function Get-PythonCandidates {
  $list = New-Object System.Collections.Generic.List[string]
  function Add-Candidate([string]$p) {
    if ($p) { [void]$list.Add($p) }
  }

  Add-Candidate $env:EW_PANEL_PYTHON
  if ($env:CONDA_PREFIX) { Add-Candidate (Join-Path $env:CONDA_PREFIX 'python.exe') }

  Add-Candidate 'D:\anaconda3\python.exe'
  Add-Candidate "$env:USERPROFILE\anaconda3\python.exe"
  Add-Candidate "$env:USERPROFILE\miniconda3\python.exe"
  Add-Candidate "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
  Add-Candidate "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"

  try {
    $where = & where.exe python 2>$null
    if ($where) {
      foreach ($line in ($where -split "`r?`n")) { Add-Candidate $line.Trim() }
    }
  } catch {}

  $uniq = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($raw in $list) {
    if (-not $raw) { continue }
    try {
      if (-not (Test-Path -LiteralPath $raw)) { continue }
      if ((Get-Item -LiteralPath $raw).PSIsContainer) {
        $raw = Join-Path $raw 'python.exe'
        if (-not (Test-Path -LiteralPath $raw)) { continue }
      }
      if ($raw -notmatch '\.exe$') { continue }
      if (Test-IsWindowsAppsStub $raw) { continue }
      $resolved = (Resolve-Path -LiteralPath $raw).Path
    } catch { continue }
    if ($uniq.Add($resolved)) { [void]$out.Add($resolved) }
  }
  return $out
}

$candidates = Get-PythonCandidates
$withSerial = @()
$withoutSerial = @()

foreach ($py in $candidates) {
  if (Test-PythonHasPyserial $py) {
    $withSerial += $py
  } else {
    $withoutSerial += $py
  }
}

if ($withSerial.Count -gt 0) {
  Write-Output $withSerial[0]
  exit 0
}

if ($InstallIfMissing -and $withoutSerial.Count -gt 0) {
  $target = $withoutSerial[0]
  Write-Host "pyserial missing, trying: $target -m pip install pyserial" -ForegroundColor Yellow
  & $target -m pip install pyserial 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0 -and (Test-PythonHasPyserial $target)) {
    Write-Output $target
    exit 0
  }
}

Write-Host '[ERROR] no Python with pyserial found' -ForegroundColor Red
Write-Host 'checked (missing pyserial):'
foreach ($py in $withoutSerial) { Write-Host "  - $py" }
Write-Host ''
Write-Host 'install on the target interpreter:'
Write-Host '  python -m pip install pyserial pillow'
Write-Host 'or set EW_PANEL_PYTHON to a python.exe that already has pyserial'
exit 1
