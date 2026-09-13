# 宿主机邮箱监听：guest 回执 / CURRENT / 纸条变化时打印唤醒行，供 Cursor notify_on_output。
# hgfs 无可靠 FileSystemWatcher，用轮询指纹。不要在本脚本里抢 COM 烧录。
$ErrorActionPreference = "Continue"
$Share = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Mail = Join-Path $Share "mailbox"
$FpFile = Join-Path $Mail "status\host_watch_fp.txt"
$IntervalSec = 8
$PendingHostHeartbeatSec = 90
$pendingHostElapsed = 0

function Get-WatchFiles {
  $out = New-Object System.Collections.Generic.List[object]
  function Add-Path($p) {
    if (Test-Path -LiteralPath $p) { [void]$out.Add((Get-Item -LiteralPath $p)) }
  }
  Add-Path (Join-Path $Mail "CURRENT.json")
  Add-Path (Join-Path $Share "FROM_GUEST_Ubuntu.txt")
  Add-Path (Join-Path $Share "GUEST_TO_HOST.txt")
  Add-Path (Join-Path $Mail "guest_to_host\HOST_PLEASE_READ.txt")
  $g2h = Join-Path $Mail "guest_to_host"
  if (Test-Path $g2h) {
    @(Get-ChildItem -LiteralPath $g2h -File -ErrorAction SilentlyContinue) |
      Where-Object { $_.Name -match '^(TASK_|REPLY_|ACK_)' } |
      ForEach-Object { [void]$out.Add($_) }
  }
  return $out
}

function Get-Fingerprint {
  $lines = Get-WatchFiles | Sort-Object FullName | ForEach-Object {
    $rel = $_.FullName.Substring($Share.Length).TrimStart("\")
    if ($_.Extension -eq ".bin") {
      "{0}|{1}" -f $rel, $_.Length
    } else {
      $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
      "{0}|{1}|{2}" -f $rel, $_.Length, $h
    }
  }
  $text = ($lines -join "`n")
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [Text.Encoding]::UTF8.GetBytes($text)
    return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
  } finally {
    $sha.Dispose()
  }
}

function Get-NewestNames {
  Get-WatchFiles | Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 5 |
    ForEach-Object { $_.Name }
}

function Read-Current {
  $p = Join-Path $Mail "CURRENT.json"
  if (-not (Test-Path $p)) { return $null }
  try {
    return Get-Content -Raw -Encoding UTF8 $p | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Emit-Wake([string]$reason) {
  $c = Read-Current
  $newest = (Get-NewestNames) -join " "
  $owner = if ($c) { $c.owner } else { "?" }
  $blocker = if ($c) { $c.blocker } else { "?" }
  $aid = if ($c) { $c.active_id } else { "?" }
  $bin = ""
  $ok = $null
  if ($c -and $c.flash) {
    $bin = [string]$c.flash.bin
    $ok = $c.flash.ok
  }
  $prompt = "Host mailbox bus: read VMware_share/mailbox/CURRENT.json and newest guest_to_host files. If owner=host execute the host task (if blocker=host_flash and flash.ok is not true, flash CURRENT.flash.bin on COM7 at 0x12010000, write mailbox/host_to_guest/REPLY_*_FLASH.md, update CURRENT). If owner is not host, summarize the receipt only. Honor CURRENT.do_not. Do not grab CH343 from guest. Do not press ESP BOOT."
  $payload = @{
    prompt  = $prompt
    reason  = $reason
    active  = $aid
    owner   = $owner
    blocker = $blocker
    bin     = $bin
    flash_ok = $ok
    newest  = $newest
  } | ConvertTo-Json -Compress
  Write-Output ("AGENT_LOOP_WAKE_hostbus " + $payload)
}

New-Item -ItemType Directory -Force -Path (Split-Path $FpFile) | Out-Null
$fp = Get-Fingerprint
Set-Content -Path $FpFile -Value $fp -Encoding ASCII
Write-Output "mailbox_watch_host init fp=$fp interval=${IntervalSec}s share=$Share"

while ($true) {
  Start-Sleep -Seconds $IntervalSec
  $n = Get-Fingerprint
  $o = (Get-Content -Raw -ErrorAction SilentlyContinue $FpFile)
  if ($o) { $o = $o.Trim() }
  if ($n -and $n -ne $o) {
    Set-Content -Path $FpFile -Value $n -Encoding ASCII
    Emit-Wake "fingerprint_changed"
    $pendingHostElapsed = 0
    continue
  }
  $c = Read-Current
  $needHost = $c -and ($c.owner -eq "host") -and $c.flash -and ($c.flash.ok -ne $true)
  if ($needHost) {
    $pendingHostElapsed += $IntervalSec
    if ($pendingHostElapsed -ge $PendingHostHeartbeatSec) {
      $pendingHostElapsed = 0
      Emit-Wake "pending_host_task"
    }
  } else {
    $pendingHostElapsed = 0
  }
}
