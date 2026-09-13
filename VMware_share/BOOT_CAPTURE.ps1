# 复位板子并抓开机日志，用来看 ew_wifi_bringup 的 AT 交互。
# sftool 烧完会 soft_reset，抓取要抢在启动日志之前打开串口。
param([double]$Listen = 45.0, [string]$Bin = "artifacts\nuttx_wifiui.bin")
$ErrorActionPreference = "Stop"

$sftool = Join-Path (Split-Path $PSScriptRoot) "tools\sftool\sftool.exe"
$bin = Join-Path $PSScriptRoot $Bin
$out = Join-Path $PSScriptRoot "artifacts\boot_capture_latest.txt"

& $sftool -c SF32LB52 -p COM7 -b 1000000 --before default_reset --after soft_reset `
  write_flash --verify "$bin@0x12010000" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "flash failed: $LASTEXITCODE" }

$port = New-Object System.IO.Ports.SerialPort
$port.PortName = "COM7"
$port.BaudRate = 1000000
$port.DataBits = 8
$port.Parity = "None"
$port.StopBits = "One"
$port.Handshake = "None"
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.Open()

$sb = New-Object System.Text.StringBuilder
$deadline = (Get-Date).AddSeconds($Listen)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 50
  if ($port.BytesToRead -gt 0) { [void]$sb.Append($port.ReadExisting()) }
}
$port.Close()

$text = $sb.ToString()
[IO.File]::WriteAllText($out, $text)
Write-Host $text
Write-Host "---- WROTE $out ($($text.Length) chars) ----"
