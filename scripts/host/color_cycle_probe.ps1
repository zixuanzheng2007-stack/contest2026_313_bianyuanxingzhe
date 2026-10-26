# 探测屏能否变色：ew screen / fb / lvgldemo
param([string]$Port = "COM7", [int]$Baud = 1000000)

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
$sp.Write([char]3); Start-Sleep -Milliseconds 500
$sp.Write("`r`n"); Start-Sleep -Seconds 1
ReadPort $sp 1 | Out-Null

$cmds = @(
  @{ n = 'ew screen info'; w = 2 },
  @{ n = 'ew screen'; w = 5 },
  @{ n = 'fb'; w = 5 },
  @{ n = 'help ew'; w = 2 }
)

foreach ($c in $cmds) {
  Write-Host ">>> $($c.n)"
  $sp.Write("$($c.n)`r`n")
  Start-Sleep -Seconds $c.w
  $out = ReadPort $sp 3
  if ($out.Trim()) { Write-Host $out.Trim() }
}

$sp.Close()
