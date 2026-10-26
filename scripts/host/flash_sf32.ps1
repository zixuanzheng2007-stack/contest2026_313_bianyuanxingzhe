# 使用 sftool 烧录（需已有固件文件）。默认只做探测，真正烧录需传 -Firmware。
# 例：
#   powershell -ExecutionPolicy Bypass -File scripts\host\flash_sf32.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\host\flash_sf32.ps1 -Port COM9 -Firmware "D:\fw\nuttx.bin@0x12010000"
# 地址须与该镜像 ELF 的文件加载地址一致；入口地址不能作为烧录起点。

param(
  [string]$Port = "",
  [string]$Firmware = "",
  [string]$Chip = "SF32LB52",
  [int]$Baud = 1000000
)

. "$PSScriptRoot\_env.ps1"
$root = $RepoRoot
$sftool = Get-ChildItem "$root\tools\sftool" -Recurse -Filter sftool.exe -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $sftool) {
  Write-Host "未找到 tools/sftool/sftool.exe，请先下载 sftool。" -ForegroundColor Red
  exit 1
}

Write-Host "sftool: $sftool"

if (-not $Port) {
  $cands = Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.Name -match 'COM\d+' -and $_.Name -match 'CH34|WCH|USB-SERIAL|USB Serial'
  }
  if ($cands) {
    if ($cands[0].Name -match '(COM\d+)') { $Port = $Matches[1] }
  }
}

if (-not $Port) {
  Write-Host "未指定且未自动发现板 COM。请插板后： -Port COMx" -ForegroundColor Red
  Write-Host "或先运行 scripts\host\detect_and_smoke.ps1"
  exit 2
}

Write-Host "探测芯片：$Chip @ $Port"
& $sftool -c $Chip -p $Port --baud $Baud 2>&1 | Out-Host

if (-not $Firmware) {
  Write-Host @"

【烧录未执行】原因：还没有竞赛固件镜像。
需要先在 Ubuntu 全量 openvela 工程编译出 bin，例如：
  ./build.sh vendor/.../sf32lb52_devkit_lcd/ --cmake -j8
然后再例如：
  .\scripts\host\flash_sf32.ps1 -Port $Port -Firmware "nuttx.bin@0x12010000"

Windows 也可用思澈 Impeller 图形工具烧录（插 USB-UART，监控后按复位）。

"@ -ForegroundColor Yellow
  exit 0
}

Write-Host "开始 write_flash: $Firmware"
& $sftool -c $Chip -p $Port --baud $Baud write_flash $Firmware
exit $LASTEXITCODE
