$ErrorActionPreference = 'Continue'
$outDir = 'E:\openvela\contest2026_313_bianyuanxingzhe\VMware_share\artifacts'
$nshLog = Join-Path $outDir 'radar_nsh_probe.txt'
$bleLog = Join-Path $outDir 'radar_ble_scan.txt'
$bleRaw = Join-Path $outDir 'radar_ble_raw.txt'
if (Test-Path $bleRaw) { Remove-Item $bleRaw -Force }

function Invoke-Nsh([string]$cmd, [int]$waitMs = 800) {
  $port = New-Object System.IO.Ports.SerialPort 'COM7', 1000000, None, 8, One
  $port.ReadTimeout = 400
  $port.WriteTimeout = 800
  $port.DtrEnable = $true
  $port.RtsEnable = $false
  $port.Open()
  Start-Sleep -Milliseconds 150
  $port.DiscardInBuffer()
  $port.Write([char]3)
  Start-Sleep -Milliseconds 80
  $port.Write("`r`n")
  Start-Sleep -Milliseconds 80
  $port.Write($cmd + "`r`n")
  Start-Sleep -Milliseconds $waitMs
  $text = ''
  try { $text = $port.ReadExisting() } catch {}
  $port.Close()
  return $text
}

$parts = @()
$parts += "==== uname / ls ===="
$parts += Invoke-Nsh "uname -a" 800
$parts += Invoke-Nsh "ls /dev" 800
$parts += "==== hexdump ttyS1 count=128 ===="
$parts += Invoke-Nsh "hexdump /dev/ttyS1 count=128" 1600
$nsh = $parts -join "`n"
[System.IO.File]::WriteAllText($nshLog, $nsh)
Write-Output $nsh

$watcher = New-Object Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementWatcher
$watcher.ScanningMode = [Windows.Devices.Bluetooth.Advertisement.BluetoothLEScanningMode]::Active
Register-ObjectEvent -InputObject $watcher -EventName Received -SourceIdentifier BleRx -Action {
  $a = $Event.SourceEventArgs
  $name = $a.Advertisement.LocalName
  $mac = $a.BluetoothAddress.ToString('X12')
  $rssi = $a.RawSignalStrengthInDBm
  $line = "{0} rssi={1} name=[{2}]" -f $mac, $rssi, $name
  Add-Content -Path 'E:\openvela\contest2026_313_bianyuanxingzhe\VMware_share\artifacts\radar_ble_raw.txt' -Value $line
} | Out-Null
$watcher.Start()
Start-Sleep -Seconds 10
$watcher.Stop()
Start-Sleep -Milliseconds 400
Unregister-Event -SourceIdentifier BleRx -ErrorAction SilentlyContinue
Get-EventSubscriber | Where-Object { $_.SourceIdentifier -eq 'BleRx' } | Unregister-Event -ErrorAction SilentlyContinue

$uniq = @()
if (Test-Path $bleRaw) {
  $uniq = Get-Content $bleRaw | Sort-Object -Unique
}
$ld = $uniq | Where-Object { $_ -match 'LD2451|HLK|Radar|2451' }
$ble = @(
  "==== BLE 10s ===="
  "total_unique=$($uniq.Count)"
  "ld2451_hits=$($ld.Count)"
  ($ld -join "`n")
  "---- sample ----"
  ($uniq | Select-Object -First 40)
) -join "`n"
[System.IO.File]::WriteAllText($bleLog, $ble)
Write-Output $ble
