# 全量硬件排查（对照官方 J0102 + FT6146）
param([string]$Port = "COM7", [int]$Baud = 1000000)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\full_hw_check_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
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

Log "==== FULL HW CHECK $(Get-Date -Format o) $Port ===="

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.DtrEnable = $true; Start-Sleep -Milliseconds 100; $sp.DtrEnable = $false
$sp.Open()
Start-Sleep -Seconds 12
$boot = ReadPort $sp 3
Log "--- BOOT (touch/ft6146/i2c) ---"
$boot -split "`n" | Where-Object { $_ -match 'ft6146|FT6146|TOUCH|touch|i2c|I2C|LSM6|input0|lcd' } | ForEach-Object { Log $_.Trim() }

$cmds = @(
  'ls /dev',
  'i2c bus',
  'i2c dev -b 0 0x38 0x38',
  'i2c dev -b 0 0x03 0x77 -z',
  'i2c dev -b 1 0x03 0x77',
  'ew screen info',
  'ew alert warn',
  'buttons'
)

foreach ($c in $cmds) {
  Log ">>> $c"
  $sp.Write([char]3); Start-Sleep -Milliseconds 200
  $wait = if ($c -match 'dev -b') { 6 } else { 2 }
  $sp.Write("$c`r`n")
  Start-Sleep -Seconds $wait
  $out = ReadPort $sp 4
  if ($out.Trim()) { Log $out.Trim() }
}

$sp.Close()
Log "LOG: $log"
