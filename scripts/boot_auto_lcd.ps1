# 上电后自动点亮屏幕：监听 COM7，启动完成即发 fb + lvgldemo
param(
  [string]$Port = "COM7",
  [int]$Baud = 1000000,
  [int]$WatchSec = 120
)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\boot_auto_lcd_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log([string]$s) { Write-Host $s; Add-Content $log $s -Encoding UTF8 }

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return $b
}

Log "==== BOOT AUTO LCD $(Get-Date -Format o) $Port (watch ${WatchSec}s) ===="

$deadline = (Get-Date).AddSeconds($WatchSec)
$opened = $false
$done = $false

while ((Get-Date) -lt $deadline -and -not $done) {
  $names = @([System.IO.Ports.SerialPort]::GetPortNames())
  if ($names -notcontains $Port) {
    Start-Sleep -Seconds 2
    continue
  }

  try {
    if (-not $opened) {
      $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
      $sp.DtrEnable = $false
      $sp.RtsEnable = $false
      $sp.Open()
      $opened = $true
      Log "Opened $Port, waking NSH..."
      $sp.Write("`r`n")
      Start-Sleep -Milliseconds 800
      $sp.Write("`r`n")
      Start-Sleep -Milliseconds 500
    }

    $chunk = ReadPort $sp 2
    if ($chunk -match 'nsh>') {
      Log "NSH ready -> fb + lvgldemo"
      $sp.Write([char]3); Start-Sleep -Milliseconds 300
      $sp.Write("fb`r`n")
      Start-Sleep -Seconds 4
      $sp.Write("lvgldemo`r`n")
      Start-Sleep -Seconds 3
      $out = ReadPort $sp 5
      if ($out.Trim()) { Log $out.Trim() }
      Log "Done. Screen should be lit."
      $done = $true
    }
  } catch {
    Log "retry: $($_.Exception.Message)"
    $opened = $false
    Start-Sleep -Seconds 2
  }
}

if ($opened) { try { $sp.Close() } catch {} }
if (-not $done) { Log "TIMEOUT: no nsh> in ${WatchSec}s (press RESET and rerun)"; exit 2 }
Log "LOG: $log"
exit 0
