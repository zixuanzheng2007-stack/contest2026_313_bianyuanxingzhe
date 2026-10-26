# WiFi 热点连通测试：COM7 @ 1Mbps，RTS/DTR=False
# 用法:
#   .\wifi_hotspot_test.ps1
#   .\wifi_hotspot_test.ps1 -Ssid "Pura 80 Pro+" -Password "yourpass"
#   .\wifi_hotspot_test.ps1 "Pura 80 Pro+" "yourpass"
# 说明：.ps1 的 param 会按位置绑参数，-Ssid Pura 80 Pro+ 无引号也能跑（见下方 Repair）
param(
  [string]$Port = "COM7",
  [string]$Baud = "1000000",
  [string]$BootWaitSec = "10",
  [string]$Ssid = "",
  [string]$Password = ""
)

$ErrorActionPreference = "Stop"

# 误绑：-Ssid Pura 80 Pro+ → Ssid=Pura, Port=80, Baud=Pro+
#       .\wifi_hotspot_test.ps1 Pura 80 Pro+ pass → Port=Pura, Baud=80, BootWaitSec=Pro+
$ssidParts = @()
if ($Ssid) { $ssidParts += $Ssid }
foreach ($tok in @($Port, $Baud, $BootWaitSec)) {
  if ([string]::IsNullOrWhiteSpace($tok)) { continue }
  if ($tok -match '^COM\d+$') { continue }
  if ($tok -eq '1000000' -or $tok -eq '10') { continue }
  $ssidParts += $tok
}
if ($ssidParts.Count -gt 1) {
  $Ssid = ($ssidParts -join " ").Trim()
  $Port = "COM7"
  $Baud = "1000000"
  $BootWaitSec = "10"
}
if ([string]::IsNullOrWhiteSpace($Ssid)) {
  $Ssid = "Pura 80 Pro+"
}

$BaudNum = 1000000
if (-not [int]::TryParse($Baud, [ref]$BaudNum)) {
  Write-Error "Invalid -Baud '$Baud' (use e.g. -Baud 1000000)"
}
$Baud = $BaudNum

$BootNum = 10
if (-not [int]::TryParse($BootWaitSec, [ref]$BootNum)) {
  Write-Error "Invalid -BootWaitSec '$BootWaitSec'"
}
$BootWaitSec = $BootNum
. "$PSScriptRoot\_env.ps1"
$log = Join-Path $ArtifactsDir "wifi_hotspot_test_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
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
  # 勿发 Ctrl+C：会把 "ew" 截成 "w"
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

Write-Log "==== WIFI HOTSPOT TEST $(Get-Date -Format o) $Port @ $Baud ===="
Write-Log "Target SSID: $Ssid"

$sp = New-Object System.IO.Ports.SerialPort
$sp.PortName = $Port
$sp.BaudRate = $Baud
$sp.DataBits = 8
$sp.Parity = "None"
$sp.StopBits = "One"
$sp.Handshake = "None"
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()
Write-Log "Opened $Port (RTS/DTR off)"

Write-Log "Reset pulse..."
$sp.DtrEnable = $true
Start-Sleep -Milliseconds 120
$sp.DtrEnable = $false
Start-Sleep -Milliseconds 200

Write-Log "Boot listen ${BootWaitSec}s..."
$boot = Recv-Wait $sp $BootWaitSec
if ($boot.Trim()) {
  Write-Log "--- boot ---"
  Write-Log $boot.TrimEnd()
} else {
  Write-Log "WARN: no boot bytes — press board RESET and rerun"
  $sp.Write("`r`n")
  Start-Sleep -Milliseconds 800
  $boot = Recv-Wait $sp 3
  if ($boot.Trim()) { Write-Log $boot.TrimEnd() }
}

$all = $boot
$all += Send-Cmd $sp "ew wifi ping" 4 6
$all += Send-Cmd $sp "ew wifi probe `"$Ssid`"" 8 10
$all += Send-Cmd $sp "ew wifi scan" 50 15
$all += Send-Cmd $sp "ew wifi" 6 8

if ($Password -ne "") {
  $joinCmd = "ew wifi join `"$Ssid`" `"$Password`""
  $all += Send-Cmd $sp $joinCmd 25 10
  $all += Send-Cmd $sp "ew wifi" 6 8
}

$sp.Close()

Write-Log ""
Write-Log "==== RESULT ===="

$modemOk = $all -match '\[ew-at\] wake ok|rx=.*OK|\[ew-wifi\] online|\[ew-wifi\] connected'
$probeHit = $all -match 'probe hit|CWLAP target'
$scanHit = $all -match [regex]::Escape($Ssid)
$online = $all -match 'WIFI ON|online\s+ip=|\[ew-wifi\] online'

if ($online) {
  Write-Log "PASS: WiFi online"
  Write-Log "LOG: $log"
  exit 0
}
if ($modemOk -and ($probeHit -or $scanHit)) {
  Write-Log "PARTIAL: modem OK, saw target SSID but not online yet"
  if ($Password -eq "") {
    Write-Log "TIP: rerun with -Password to test join"
  }
  Write-Log "LOG: $log"
  exit 1
}
if ($modemOk) {
  Write-Log "PARTIAL: ESP modem responds, hotspot not in scan/probe"
  Write-Log "TIP: phone hotspot 2.4G on, within 1m; or use WiFi page manual SSID"
  Write-Log "LOG: $log"
  exit 2
}
if ($boot.Length -eq 0 -and $all -notmatch 'nsh>|ew-at|ew-wifi') {
  Write-Log "FAIL: no serial data — check USB, close sscom, press RESET"
  Write-Log "LOG: $log"
  exit 4
}

Write-Log "FAIL: modem not responding (NO MODEM / silent at every baud)"
Write-Log "LOG: $log"
exit 3
