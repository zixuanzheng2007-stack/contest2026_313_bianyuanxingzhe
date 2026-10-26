# ESP-AT WiFi 分层诊断（排查清单 A–F 的 PC 侧自动化）
# 用法:
#   .\wifi_at_diagnose.ps1
#   .\wifi_at_diagnose.ps1 -Port COM7 -ProbeSsid "Pura 80 Pro+"
# 注意: 烧录/抓日志前请先关闭 ew_panel.py / sscom（避免 COM 占用）
param(
  [string]$Port = "COM7",
  [string]$Baud = "1000000",
  [string]$BootWaitSec = "12",
  [string]$ProbeSsid = "Pura 80 Pro+"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

$BaudNum = 1000000
if (-not [int]::TryParse($Baud, [ref]$BaudNum)) {
  Write-Error "Invalid -Baud '$Baud'"
}
$BootNum = 12
if (-not [int]::TryParse($BootWaitSec, [ref]$BootNum)) {
  Write-Error "Invalid -BootWaitSec '$BootWaitSec'"
}

$log = Join-Path $ArtifactsDir "wifi_at_diagnose_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

function Write-Log([string]$s) {
  Write-Host $s
  Add-Content -Path $log -Value $s -Encoding UTF8
}

function Recv-Wait($sp, [double]$sec) {
  $sb = New-Object System.Text.StringBuilder
  $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try {
      if ($sp.BytesToRead -gt 0) {
        [void]$sb.Append($sp.ReadExisting())
      }
    } catch {}
    Start-Sleep -Milliseconds 50
  }
  return $sb.ToString()
}

function Send-Cmd($sp, [string]$cmd, [double]$waitSec, [double]$recvSec) {
  Write-Log ""
  Write-Log ">>> $cmd"
  $sp.Write("`r`n")
  Start-Sleep -Milliseconds 300
  $sp.Write("$cmd`r`n")
  Start-Sleep -Seconds $waitSec
  $out = Recv-Wait $sp $recvSec
  if ($out.Trim()) {
    Write-Log $out.TrimEnd()
  } else {
    Write-Log "(no output)"
  }
  return $out
}

Write-Log "=== WiFi AT diagnose ==="
Write-Log "Port=$Port Baud=$Baud Log=$log"
Write-Log "ProbeSsid=$ProbeSsid"
Write-Log ""

if (-not (Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue |
    Where-Object { $_.DeviceID -eq $Port })) {
  Write-Log "WARN: $Port not found — plug board in and close ew_panel/sscom first."
}

Add-Type -AssemblyName System.IO.Ports
$sp = New-Object System.IO.Ports.SerialPort $Port, $BaudNum, None, 8, one
$sp.Handshake = [System.IO.Ports.Handshake]::None
$sp.RtsEnable = $false
$sp.DtrEnable = $false
$sp.ReadTimeout = 500
$sp.WriteTimeout = 500
$sp.NewLine = "`n"
$sp.Open()
Start-Sleep -Seconds 1
[void](Recv-Wait $sp 1.5)

Write-Log "--- boot wait ${BootNum}s ---"
Start-Sleep -Seconds $BootNum
[void](Recv-Wait $sp 2)

# 14 步验收脚本（与固件排查清单 F 对齐）
Send-Cmd $sp "ew wifi ping" 2 8
Send-Cmd $sp "ew at AT" 1 3
Send-Cmd $sp "ew at AT+GMR" 1 4
Send-Cmd $sp "ew at AT+CWMODE=1" 1 3
Send-Cmd $sp "ew at AT+CWMODE?" 1 3
Send-Cmd $sp "ew at AT+CWLAP" 3 55
Send-Cmd $sp "ew wifi scan" 2 90
if ($ProbeSsid) {
  $quoted = if ($ProbeSsid -match '\s') { "`"$ProbeSsid`"" } else { $ProbeSsid }
  Send-Cmd $sp "ew wifi probe $quoted" 2 25
}
Send-Cmd $sp "ew wifi raw" 2 12
Send-Cmd $sp "ew at AT+CIPSTA?" 1 4

Write-Log ""
Write-Log "=== done ==="
Write-Log "Compare: ew at AT+CWLAP raw vs ew wifi scan list"
Write-Log "If CWLAP has APs but scan is empty -> parser/RX issue in ew_wifi_at.c"
Write-Log "If AT silent -> UART/pins/baud/ESP-AT firmware"

$sp.Close()
Write-Host ""
Write-Host "Log saved: $log"
