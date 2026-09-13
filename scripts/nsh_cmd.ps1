# 发单条 NSH 命令并读回显
param(
  [Parameter(Mandatory = $true)][string]$Cmd,
  [string]$Port = "COM7",
  [int]$Baud = 1000000,
  [int]$WaitSec = 5
)

function ReadPort($sp, [int]$sec) {
  $b = ''; $end = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $end) {
    try { if ($sp.BytesToRead -gt 0) { $b += $sp.ReadExisting() } } catch {}
    Start-Sleep -Milliseconds 80
  }
  return $b
}

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.Open()
$sp.Write([char]3); Start-Sleep -Milliseconds 400
$sp.Write("`r`n"); Start-Sleep -Milliseconds 600
ReadPort $sp 1 | Out-Null
Write-Host ">>> $Cmd"
$sp.Write("$Cmd`r`n")
Start-Sleep -Seconds $WaitSec
$out = ReadPort $sp 8
if ($out.Trim()) { Write-Host $out.Trim() } else { Write-Host "(no echo — demo 可能已占屏)" }
$sp.Close()
