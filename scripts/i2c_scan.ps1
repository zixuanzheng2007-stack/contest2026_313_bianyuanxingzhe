# I2C 双总线扫描（先 Ctrl+C 退出 demo）
param(
  [string]$Port = "COM7",
  [int]$Baud = 1000000
)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\i2c_scan_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log([string]$s) { Write-Host $s; Add-Content $log $s -Encoding UTF8 }

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return ($b -replace '\x1b\[[0-9;?]*[0-9;]*[a-zA-Z]', '')
}

Log "==== I2C SCAN $(Get-Date -Format o) $Port ===="

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.Open()
$sp.Write([char]3); Start-Sleep -Milliseconds 500
$sp.Write([char]3); Start-Sleep -Milliseconds 500
$sp.Write("`r`n"); Start-Sleep -Seconds 1
ReadPort $sp 1 | Out-Null

$cmds = @(
  'i2c bus',
  'i2c dev -b 0 0x08 0x77',
  'i2c dev -b 1 0x03 0x77',
  'i2c dev -b 1 -z 0x03 0x77'
)

foreach ($c in $cmds) {
  Log ">>> $c"
  $wait = if ($c -match 'dev') { 6 } else { 2 }
  $sp.Write("$c`r`n")
  Start-Sleep -Seconds $wait
  $out = ReadPort $sp 4
  if ($out.Trim()) { Log $out.Trim() }
}

$sp.Close()
Log "LOG: $log"
