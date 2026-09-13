# 后台启动 mailbox 动态监听（供 Cursor notify_on_output 捕获 AGENT_LOOP_WAKE_hostbus）。
param(
  [int]$IntervalSec = 8,
  [switch]$NoAutoExec,
  [switch]$Foreground
)
$ErrorActionPreference = "Stop"
$Loop = Join-Path $PSScriptRoot "mailbox_bus_loop.ps1"
$Share = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Share "mailbox\status\host_bus_loop.pid"

if (-not (Test-Path $Loop)) { throw "missing $Loop" }

$args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Loop, "-IntervalSec", $IntervalSec)
if ($NoAutoExec) { $args += "-NoAutoExec" }

if ($Foreground) {
  & powershell @args
  exit $LASTEXITCODE
}

$existing = Get-Content -ErrorAction SilentlyContinue $PidFile
if ($existing) {
  $p = Get-Process -Id ([int]$existing) -ErrorAction SilentlyContinue
  if ($p) {
    Write-Host "already running pid=$existing (use -Foreground to replace)"
    exit 0
  }
}

$proc = Start-Process powershell -ArgumentList $args -PassThru -WindowStyle Hidden
Set-Content -Path $PidFile -Value $proc.Id -Encoding ASCII
Write-Host "mailbox_bus_loop pid=$($proc.Id) interval=${IntervalSec}s"
Write-Host "log: VMware_share\mailbox\status\HOST_EXEC.log"
Write-Host "stop: Stop-Process -Id $($proc.Id); remove pid file"
