$Share = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Share "mailbox\status\host_bus_loop.pid"
$id = Get-Content -ErrorAction SilentlyContinue $PidFile
if (-not $id) { Write-Host "not running"; exit 0 }
Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue
Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
Write-Host "stopped pid=$id"
