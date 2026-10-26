# 边缘行者 · DevKit 实时屏镜像 + 串口遥控面板
# 用法: .\EW_PANEL.ps1
param(
  [switch]$InstallDeps
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script = Join-Path $root "tools\ew_panel.py"
$artifacts = Join-Path $root "VMware_share\artifacts"
$resolve = Join-Path $PSScriptRoot "resolve_panel_python.ps1"

if (-not (Test-Path $resolve)) {
  Write-Host "缺少 $resolve" -ForegroundColor Red
  exit 1
}

$resolveArgs = @()
if ($InstallDeps) { $resolveArgs += '-InstallIfMissing' }
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
try {
  $py = & $resolve @resolveArgs
} finally {
  $ErrorActionPreference = $prevEap
}
if ($LASTEXITCODE -ne 0 -or -not $py) { exit 1 }

Write-Host "使用 Python: $py" -ForegroundColor DarkGray

$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -like "*$script*"
} | Select-Object -First 1
if ($running) {
  Add-Type @'
using System;
using System.Runtime.InteropServices;
public class EwPanelWindow {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
  $process = Get-Process -Id $running.ProcessId -ErrorAction SilentlyContinue
  if ($process -and $process.MainWindowHandle -ne 0) {
    [EwPanelWindow]::ShowWindow($process.MainWindowHandle, 9) | Out-Null
    [EwPanelWindow]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
  }
  exit 0
}

New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Start-Process -WorkingDirectory $root -FilePath $py -ArgumentList $script `
  -RedirectStandardOutput (Join-Path $artifacts "ew_panel_$stamp.stdout.log") `
  -RedirectStandardError (Join-Path $artifacts "ew_panel_$stamp.stderr.log") `
  -WindowStyle Normal
