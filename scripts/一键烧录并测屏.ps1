# 一键：烧录 + 自动 NSH 测屏（不用手打命令）
# 用法：右键「使用 PowerShell 运行」，或：
#   powershell -ExecutionPolicy Bypass -File scripts\一键烧录并测屏.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$sf = Join-Path $root "tools\sftool\sftool.exe"
$bin = Join-Path $root "VMware_share\artifacts\nuttx.bin"
$log = Join-Path $root "VMware_share\artifacts\一键测屏_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Log([string]$s) { Write-Host $s; Add-Content $log $s -Encoding UTF8 }

Log "==== 1/3 烧录固件 ===="
if (-not (Test-Path $sf)) { Log "缺少 tools\sftool\sftool.exe"; exit 1 }
if (-not (Test-Path $bin)) { Log "缺少 $bin"; exit 1 }
& $sf -c SF32LB52 -p COM7 -b 1000000 write_flash --verify "$bin@0x12010000" 2>&1 | Tee-Object -Append $log
if ($LASTEXITCODE -ne 0) {
  Log "1000000 失败，试 115200 compat..."
  & $sf -c SF32LB52 -p COM7 -b 115200 --compat true write_flash --verify "$bin@0x12010000" 2>&1 | Tee-Object -Append $log
}
Log "flash_exit=$LASTEXITCODE"

Log "==== 2/3 进 NSH（自动发命令）===="
Start-Sleep -Seconds 2
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "nsh_auto.ps1") -Port COM7 -BootWaitSec 8 -Commands "ls /dev","ew alert warn","lvgldemo" 2>&1 | Tee-Object -Append $log

Log "==== 3/3 完成 ===="
Log "请看屏幕是否亮/有 UI；日志: $log"
Log "若仍黑屏：检查 22P FPC 软排线是否插到底（不是 40P 雷达排针）"
