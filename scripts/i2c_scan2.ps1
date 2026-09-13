param([string]$Port = "COM7", [int]$Baud = 1000000)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\i2c_scan2_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"

function Log([string]$s) { Write-Host $s; Add-Content $log $s -Encoding UTF8 }

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return $b
}

Log "==== I2C SCAN2 $(Get-Date -Format o) ===="

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()

for ($i = 0; $i -lt 3; $i++) {
  $sp.Write([char]3); Start-Sleep -Milliseconds 400
}
$sp.Write("`r`n"); Start-Sleep -Milliseconds 800
$sp.Write("`r`n"); Start-Sleep -Seconds 2
$wake = ReadPort $sp 3
Log "wake: [$($wake.Trim())]"

foreach ($c in @('ls /dev', 'i2c bus', 'i2c dev -b 0 0x08 0x77', 'i2c dev -b 1 0x03 0x77')) {
  Log ">>> $c"
  $sp.Write("$c`r`n")
  Start-Sleep -Seconds 5
  $o = ReadPort $sp 5
  Log $o.Trim()
}

$sp.Close()
Log "LOG: $log"
