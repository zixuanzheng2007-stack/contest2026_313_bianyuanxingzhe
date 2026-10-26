# 验证上电自启 lvgldemo（不应手动发命令）
param([string]$Port = "COM7", [int]$Baud = 1000000)

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return $b
}

Write-Host "==== BOOT CHECK $(Get-Date -Format o) ===="
$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.DtrEnable = $true; $sp.RtsEnable = $false
$sp.Open()
Start-Sleep -Milliseconds 150
$sp.DtrEnable = $false
Write-Host "DTR reset pulse sent, listening 20s..."
Start-Sleep -Seconds 20
$out = ReadPort $sp 5
if ($out -match 'lv_nuttx_lcd_create|lvgldemo|LVGL') {
  Write-Host "PASS: auto lvgldemo detected"
} else {
  Write-Host "WARN: no LVGL boot log yet"
}
if ($out.Trim()) { Write-Host $out.Trim() }
$sp.Close()
