# 自动连 COM7，复位板子，发送 NSH 命令并保存日志（不用手打 nsh）
param(
  [string]$Port = "COM7",
  [int]$Baud = 1000000,
  [int]$BootWaitSec = 12,
  [string[]]$Commands = @("help", "uname -a", "ls /dev", "lvgldemo")
)

$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "VMware_share\artifacts"
$log = Join-Path $outDir "nsh_auto_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Write-Log([string]$s) {
  Write-Host $s
  Add-Content -Path $log -Value $s -Encoding UTF8
}

Write-Log "==== NSH AUTO $(Get-Date -Format o) $Port @ $Baud ===="

try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
  $sp.ReadTimeout = 300
  $sp.WriteTimeout = 1000
  $sp.NewLine = "`n"
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Write-Log "Opened $Port"

  # 软复位：部分 CH343 板子 DTR 会拉 RESET
  Write-Log "Toggle DTR/RTS reset pulse..."
  $sp.DtrEnable = $true
  Start-Sleep -Milliseconds 100
  $sp.DtrEnable = $false
  Start-Sleep -Milliseconds 200
  $sp.RtsEnable = $true
  Start-Sleep -Milliseconds 100
  $sp.RtsEnable = $false

  Write-Log "Waiting ${BootWaitSec}s for boot (若仍无输出请按板子 RESET 一次)..."
  $buf = New-Object System.Text.StringBuilder
  $end = (Get-Date).AddSeconds($BootWaitSec)
  while ((Get-Date) -lt $end) {
    try {
      if ($sp.BytesToRead -gt 0) {
        $chunk = $sp.ReadExisting()
        [void]$buf.Append($chunk)
        Write-Host -NoNewline $chunk
      }
    } catch {}
    Start-Sleep -Milliseconds 80
  }
  $boot = $buf.ToString()
  Write-Log ""
  Write-Log "--- boot capture ($($boot.Length) chars) ---"
  Write-Log $boot

  if ($boot -notmatch 'nsh>') {
    Write-Log "Send Enter to wake NSH..."
    $sp.Write("`r`n")
    Start-Sleep -Milliseconds 800
    $wake = $sp.ReadExisting()
    Write-Host -NoNewline $wake
    Write-Log $wake
  }

  foreach ($cmd in $Commands) {
    Write-Log ""
    Write-Log ">>> $cmd"
    $sp.Write("$cmd`r`n")
    Start-Sleep -Milliseconds 1200
    $resp = ""
    $tend = (Get-Date).AddSeconds(3)
    while ((Get-Date) -lt $tend) {
      try {
        if ($sp.BytesToRead -gt 0) {
          $resp += $sp.ReadExisting()
        }
      } catch {}
      Start-Sleep -Milliseconds 80
    }
    Write-Host $resp
    Write-Log $resp
  }

  $sp.Close()
  Write-Log ""
  Write-Log "LOG: $log"
  if ($boot.Length -eq 0 -and $resp.Length -eq 0) {
    Write-Log "FAIL: no serial data. Check USB-UART cable, close PuTTY/sscom, press RESET."
    exit 2
  }
  if ($boot + $resp -match 'nsh>') {
    Write-Log "PASS: NSH detected"
    exit 0
  }
  Write-Log "WARN: got data but no nsh> prompt"
  exit 1
} catch {
  Write-Log "ERROR: $($_.Exception.Message)"
  exit 4
}
