# 开发板冒烟：对比插拔前后 COM 口变化
# 用法：先运行一次（未插板）→ 插上板后再运行一次

Write-Host "==== $(Get-Date -Format 'HH:mm:ss') COM 口快照 ====" -ForegroundColor Cyan
Get-PnpDevice -Class Ports -Status OK -ErrorAction SilentlyContinue |
  Sort-Object FriendlyName |
  Format-Table Status, FriendlyName -AutoSize

Write-Host "==== 详细 ====" -ForegroundColor Cyan
Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'COM\d+' } |
  Select-Object Name, DeviceID, Status |
  Format-Table -AutoSize

Write-Host @"

操作提示：
1. 未插板时运行本脚本，记下现有 COM。
2. 用【数据线】插开发板丝印【USB to UART / USB转串口】口（不要插错另一个 Type-C）。
3. 看电源灯是否亮；再运行本脚本，找出【新增】的 COM（常见名称含 CH340/CH34x/USB-SERIAL）。
4. 用 PuTTY：Connection type = Serial，Serial line = 该 COMx，Speed = 1000000（若乱码再试 115200）。
5. 打开后按一下板上复位键，应出现 NSH / 启动日志。

"@
