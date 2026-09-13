# 换测试界面：fb 色块 / ew alert / buttons / hello（不用 lvgldemo）
param(
  [string]$Port = "",
  [int]$Baud = 1000000
)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\screen_test_ui_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Log([string]$s) { Write-Host $s; Add-Content $log $s -Encoding UTF8 }

if (-not $Port) {
  $c = Get-CimInstance Win32_PnPEntity -EA SilentlyContinue |
    Where-Object { $_.Name -match 'COM\d+' -and $_.Name -match 'CH34|CH343|WCH' }
  if ($c -and $c[0].Name -match '(COM\d+)') { $Port = $Matches[1] }
}
if (-not $Port) { Log "FAIL: no COM"; exit 2 }

Log "==== SCREEN UI TEST $(Get-Date -Format o) $Port ===="

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return ($b -replace '\x1b\[[0-9;?]*[0-9;]*[a-zA-Z]', '')
}

try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
  $sp.ReadTimeout = 300
  $sp.Open()
  $sp.Write([char]3); Start-Sleep -Milliseconds 400
  $sp.Write("`r`n"); Start-Sleep -Milliseconds 600
  ReadPort $sp 1 | Out-Null

  $cmds = @(
    @{ n = 'uname -a'; w = 2 },
    @{ n = 'ls /dev'; w = 2 },
    @{ n = 'fb'; w = 5 },
    @{ n = 'ew alert warn'; w = 2 },
    @{ n = 'ew alert crit'; w = 2 },
    @{ n = 'ew alert none'; w = 2 },
    @{ n = 'hello'; w = 2 },
    @{ n = 'buttons'; w = 3 },
    @{ n = 'i2c dev -b 1 0x03 0x77'; w = 6 }
  )

  foreach ($c in $cmds) {
    Log ">>> $($c.n)"
    $sp.Write("$($c.n)`r`n")
    Start-Sleep -Seconds $c.w
    $out = ReadPort $sp 2
    if ($out.Trim()) { Log $out.Trim() }
    if ($c.n -eq 'fb') { Log "(看屏：fb 应画彩色矩形，约 3 秒)" }
  }

  $sp.Close()
  Log "LOG: $log"
  exit 0
} catch {
  Log "ERROR: $($_.Exception.Message)"
  exit 4
}
