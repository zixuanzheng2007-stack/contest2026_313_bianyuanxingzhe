# 自动发 lvgldemo（先 Ctrl+C 退出占屏程序）
param(
  [string]$Port = "COM7",
  [int]$Baud = 1000000
)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "VMware_share\artifacts\lvgldemo_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
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

Log "==== LVGLDEMO $(Get-Date -Format o) $Port ===="

try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
  $sp.ReadTimeout = 300
  $sp.Open()
  Log "Opened $Port"
  Start-Sleep -Milliseconds 300
  $sp.DiscardInBuffer()

  # 退出可能正在跑的 demo / ew
  $sp.Write([char]3)
  Start-Sleep -Milliseconds 600
  $sp.Write([char]3)
  Start-Sleep -Milliseconds 600
  $sp.Write("`r`n")
  Start-Sleep -Milliseconds 800
  $sp.DiscardInBuffer()
  $wake = ReadPort $sp 2
  if ($wake.Trim()) { Log "wake: $($wake.Trim())" }

  Log ">>> lvgldemo"
  Log "(请看屏幕：应出现 LVGL 按钮界面)"
  $sp.DiscardInBuffer()
  $sp.Write("lvgldemo`r`n")

  Start-Sleep -Seconds 15
  $out = ReadPort $sp 12
  if ($out.Trim()) { Log $out.Trim() }

  $sp.Close()
  Log "LOG: $log"
  if ($out -match 'lvgldemo|LVGL|open success|nsh>') {
    Log "PASS: command sent, check screen for UI"
    exit 0
  }
  Log "WARN: little serial echo — 若屏有 UI 仍算成功"
  exit 0
} catch {
  Log "ERROR: $($_.Exception.Message)"
  exit 4
}
