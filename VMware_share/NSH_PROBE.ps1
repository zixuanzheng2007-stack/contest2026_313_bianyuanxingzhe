# 抓 COM7 控制台，确认新固件的 WiFi/UI 日志。1Mbps 8N1，RTS/DTR 必须 False。
param(
  [double]$Listen = 25.0,
  [string[]]$Cmds = @("ew wifi", "ew wifi scan")
)
$ErrorActionPreference = "Stop"
$out = Join-Path $PSScriptRoot "artifacts\nsh_probe_latest.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

function Recv-Wait($port, [double]$sec) {
  $deadline = (Get-Date).AddSeconds($sec)
  $sb = New-Object System.Text.StringBuilder
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 50
    if ($port.BytesToRead -gt 0) { [void]$sb.Append($port.ReadExisting()) }
  }
  return $sb.ToString()
}

$port = New-Object System.IO.Ports.SerialPort
$port.PortName = "COM7"
$port.BaudRate = 1000000
$port.DataBits = 8
$port.Parity = "None"
$port.StopBits = "One"
$port.Handshake = "None"
$port.DtrEnable = $false
$port.RtsEnable = $false
$port.ReadTimeout = 800
$port.Open()

$log = New-Object System.Text.StringBuilder
[void]$log.AppendLine("==== passive listen ${Listen}s ====")
[void]$log.AppendLine((Recv-Wait $port $Listen))

foreach ($c in $Cmds) {
  [void]$log.AppendLine("==== cmd: $c ====")
  $port.DiscardInBuffer()
  $port.Write($c + "`r")
  [void]$log.AppendLine((Recv-Wait $port 20.0))
}
$port.Close()

$text = $log.ToString()
[IO.File]::WriteAllText($out, $text)
Write-Host $text
Write-Host "WROTE $out"
