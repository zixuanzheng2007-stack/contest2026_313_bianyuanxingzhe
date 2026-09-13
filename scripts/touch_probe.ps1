# 触屏自检：I2C 扫描 + lvgldemo 触摸驱动日志
param(
  [string]$Port = "",
  [int]$Baud = 1000000
)

$root = Split-Path $PSScriptRoot -Parent
$outDir = Join-Path $root "VMware_share\artifacts"
$log = Join-Path $outDir "touch_probe_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Log([string]$s) {
  Write-Host $s
  Add-Content -Path $log -Value $s -Encoding UTF8
}

function Get-BoardCom {
  $c = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'COM\d+' -and $_.Name -match 'CH34|CH343|WCH|USB-SERIAL|USB Serial' }
  if ($c -and $c[0].Name -match '(COM\d+)') { return $Matches[1] }
  return $null
}

if (-not $Port) { $Port = Get-BoardCom }
if (-not $Port) {
  Log "FAIL: no CH343 COM. Plug USB-UART cable."
  exit 2
}

Log "==== TOUCH PROBE $(Get-Date -Format o) $Port @ $Baud ===="

function Read-SerialFor([System.IO.Ports.SerialPort]$sp, [int]$seconds) {
  $sb = New-Object System.Text.StringBuilder
  $end = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $end) {
    try {
      if ($sp.BytesToRead -gt 0) { [void]$sb.Append($sp.ReadExisting()) }
    } catch {}
    Start-Sleep -Milliseconds 80
  }
  return $sb.ToString()
}

function Send-Cmd([System.IO.Ports.SerialPort]$sp, [string]$cmd, [int]$waitSec) {
  Log ">>> $cmd"
  $sp.Write("$cmd`r`n")
  Start-Sleep -Milliseconds 500
  $r = Read-SerialFor $sp $waitSec
  $clean = $r -replace '\x1b\[[0-9;?]*[0-9;]*[a-zA-Z]', ''
  if ($clean.Trim().Length -gt 0) { Log $clean.Trim() }
  return $clean
}

try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
  $sp.ReadTimeout = 300
  $sp.WriteTimeout = 1000
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Log "Opened $Port"

  $sp.DtrEnable = $true
  Start-Sleep -Milliseconds 100
  $sp.DtrEnable = $false
  Start-Sleep -Seconds 14
  Send-Cmd $sp "`r`n" 2 | Out-Null

  Log "--- boot (ft6146 / LSM6 / touch errors) ---"
  $boot = Read-SerialFor $sp 2
  $boot -split "`n" | Where-Object {
    $_ -match 'ft6146|FT6146|LSM6|touch|TOUCH|read id|id_h|ERROR|WARN'
  } | ForEach-Object { Log $_.Trim() }

  Send-Cmd $sp "ls /dev" 3 | Out-Null
  Send-Cmd $sp "i2c bus" 3 | Out-Null
  # FT6146: hardware I2C1 -> NuttX /dev/i2c0, addr 0x38
  Send-Cmd $sp "i2c dev -b 0 0x38 0x38" 5 | Out-Null
  Send-Cmd $sp "i2c dev -b 0 0x03 0x77 -z" 8 | Out-Null
  Send-Cmd $sp "i2c dev -b 1 0x03 0x77" 6 | Out-Null

  Log ">>> lvgldemo (capture 12s — 请在屏上点几下)"
  $sp.Write("lvgldemo`r`n")
  Start-Sleep -Milliseconds 1000
  $lv = Read-SerialFor $sp 12
  $lvClean = $lv -replace '\x1b\[[0-9;?]*[0-9;]*[a-zA-Z]', ''
  $hits = $lvClean -split "`n" | Where-Object {
    $_ -match 'touch|input0|i2c|CTP|GT|CST|LVGL|error|fail|open success'
  }
  if ($hits) {
    Log "--- lvgldemo filtered ---"
    $hits | ForEach-Object { Log $_.Trim() }
  } else {
    Log "(no touch keywords in lvgldemo output, raw len=$($lv.Length))"
    if ($lvClean.Length -lt 3000) { Log $lvClean.Trim() }
  }

  Log ">>> summary"
  $summary = Get-Content $log -Raw -Encoding UTF8
  if ($summary -match 'input0') { Log "OK: input0 in ls /dev" } else { Log "WARN: input0 not seen" }
  if ($summary -match 'touchscreen.*open success') { Log "OK: touch driver open success" }
  elseif ($summary -match 'touchscreen') { Log "WARN: touch messages but check open success" }
  else { Log "WARN: no touch driver log from lvgldemo" }
  if ($summary -match '38:\s*38|0x38.*ACK|DEVICE.*0x38') { Log "OK: FT6146 0x38 seen on bus0" }
  elseif ($summary -match '30:\s*(?!--)') { Log "OK: I2C device(s) in 0x30 row on bus0" }
  else { Log "WARN: bus0 no 0x38 — check sifli_ap PA30 patch + FPC 18-21" }
  if ($summary -match 'id_h=0x') { Log "OK: ft6146 chip ID read at boot" }
  else { Log "WARN: no ft6146 id_h in boot log" }

  $sp.Close()
  Log "LOG: $log"
  exit 0
} catch {
  Log "ERROR: $($_.Exception.Message)"
  exit 4
}
