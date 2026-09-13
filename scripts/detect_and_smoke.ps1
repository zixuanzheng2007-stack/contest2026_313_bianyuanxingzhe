param(
  [int]$WaitSec = 0,
  [int]$Baud = 1000000,
  [string]$Port = ""
)

function Get-BoardCandidates {
  Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -match 'COM\d+' -and
      $_.Name -notmatch 'Bluetooth|BTHENUM' -and
      (
        $_.Name -match 'CH34|WCH|USB-SERIAL|USB Serial|Silicon|CDC' -or
        $_.DeviceID -match 'VID_1A86|VID_067B|VID_10C4|CH34'
      )
    }
}

function Get-ComFromName([string]$name) {
  if ($name -match '(COM\d+)') { return $Matches[1] }
  return $null
}

Write-Host "==== USB-UART detect ====" -ForegroundColor Cyan
Write-Host "All COM devices:"
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'COM\d+' } |
  ForEach-Object { "  - $($_.Name)" }

$cands = @(Get-BoardCandidates)
if ($WaitSec -gt 0 -and $cands.Count -eq 0) {
  Write-Host "No board COM yet. Waiting up to ${WaitSec}s. Plug data cable to USB-to-UART now..." -ForegroundColor Yellow
  $deadline = (Get-Date).AddSeconds($WaitSec)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $cands = @(Get-BoardCandidates)
    if ($cands.Count -gt 0) { break }
    Write-Host "." -NoNewline
  }
  Write-Host ""
}

if (-not $Port) {
  if ($cands.Count -eq 0) {
    Write-Host ""
    Write-Host "[FAIL] No DevKit USB-UART (CH340/CH34x) found." -ForegroundColor Red
    Write-Host "Checklist:"
    Write-Host "  1) Use a DATA Type-C cable (not charge-only)"
    Write-Host "  2) Plug the port labeled USB to UART (not the other Type-C)"
    Write-Host "  3) Power LED should be on"
    Write-Host "  4) If still no COM, install WCH CH34x driver and replug"
    Write-Host "Then rerun with: -WaitSec 60"
    exit 2
  }
  $Port = Get-ComFromName $cands[0].Name
  Write-Host "Selected: $($cands[0].Name) -> $Port" -ForegroundColor Green
} else {
  Write-Host "Using port: $Port" -ForegroundColor Green
}

Write-Host "==== Serial smoke read (baud=$Baud) ====" -ForegroundColor Cyan
try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
  $sp.ReadTimeout = 500
  $sp.WriteTimeout = 500
  $sp.DtrEnable = $false
  $sp.RtsEnable = $false
  $sp.Open()
  Write-Host "Opened $Port. Press RESET on board within 8 seconds..." -ForegroundColor Yellow
  $buf = New-Object System.Text.StringBuilder
  $end = (Get-Date).AddSeconds(8)
  while ((Get-Date) -lt $end) {
    try {
      if ($sp.BytesToRead -gt 0) {
        $chunk = $sp.ReadExisting()
        [void]$buf.Append($chunk)
        Write-Host -NoNewline $chunk
      }
    } catch {}
    Start-Sleep -Milliseconds 50
  }
  $sp.Close()
  $text = $buf.ToString()
  Write-Host ""
  if ($text.Length -gt 0) {
    Write-Host "[OK] Received $($text.Length) chars." -ForegroundColor Green
    if ($text -match 'nsh>|NuttShell|SF32|vela|siFli|SiFli') {
      Write-Host "[PASS] Console-like output detected." -ForegroundColor Green
      exit 0
    }
    Write-Host "[WARN] Data received but no NSH keyword. Try -Baud 115200 or check firmware." -ForegroundColor Yellow
    exit 0
  }
  Write-Host "[WARN] No data. Press reset; try -Baud 115200; close other serial apps." -ForegroundColor Yellow
  exit 3
} catch {
  Write-Host "[FAIL] Open serial failed: $($_.Exception.Message)" -ForegroundColor Red
  exit 4
}
