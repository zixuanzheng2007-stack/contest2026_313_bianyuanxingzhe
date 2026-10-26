# 宿主机 mailbox 总线：轮询共享盘指纹 → 自动执行 host 任务 → 打印 AGENT_LOOP_WAKE 唤醒 Cursor。
param(
  [int]$IntervalSec = 8,
  [switch]$NoAutoExec
)
$ErrorActionPreference = "Continue"
$Share = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Mail = Join-Path $Share "mailbox"
$FpFile = Join-Path $Mail "status\host_watch_fp.txt"
$Exec = Join-Path $PSScriptRoot "mailbox_exec_host.ps1"
$PendingHostHeartbeatSec = 300
$pendingHostElapsed = 0
$lastWakeState = ""

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
  } finally { $sha.Dispose() }
}

function Read-Current {
  $p = Join-Path $Mail "CURRENT.json"
  if (-not (Test-Path $p)) { return $null }
  try { return Get-Content -Raw -Encoding UTF8 $p | ConvertFrom-Json } catch { return $null }
}

function Invoke-AutoExec {
  if ($NoAutoExec) { return $null }
  if (-not (Test-Path $Exec)) { return @{ error = "no_exec_script" } }
  try {
    $raw = & powershell -NoProfile -ExecutionPolicy Bypass -File $Exec 2>&1 | Out-String
    return @{ raw = $raw.Trim() }
  } catch {
    return @{ error = $_.Exception.Message }
  }
}

function Emit-Wake([string]$reason, $execResult) {
  $c = Read-Current
  $newest = (Get-WatchFiles | Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 5 | ForEach-Object { $_.Name }) -join " "
  $prompt = @"
Host mailbox bus AUTO: Read VMware_share/mailbox/CURRENT.json and newest guest_to_host/*.md.
If owner=host: execute host.need (screen/NSH/REPLY per AGENT_BUS.md). Check mailbox/status/HOST_EXEC.log for auto-flash.
If owner=guest: summarize only. Honor do_not. Do not grab CH343 from guest. Do not ESP BOOT.
"@
  $payload = @{
    prompt  = $prompt.Trim()
    reason  = $reason
    active  = if ($c) { [string]$c.active_id } else { "?" }
    owner   = if ($c) { [string]$c.owner } else { "?" }
    blocker = if ($c) { [string]$c.blocker } else { "?" }
    exec    = $execResult
    newest  = $newest
  } | ConvertTo-Json -Compress
  Write-Output ("AGENT_LOOP_WAKE_hostbus " + $payload)
}

function Get-WakeState {
  $c = Read-Current
  if (-not $c) { return "none" }
  return ("{0}|{1}|{2}" -f [string]$c.owner, [string]$c.blocker, [string]$c.active_id)
}

function Handle-Tick([string]$reason, [switch]$AllowDuplicate) {
  $state = Get-WakeState
  if (-not $AllowDuplicate -and $reason -eq "pending_host_task" -and $state -eq $script:lastWakeState) {
    return
  }
  $script:lastWakeState = $state
  $execResult = Invoke-AutoExec
  Emit-Wake $reason $execResult
}

New-Item -ItemType Directory -Force -Path (Split-Path $FpFile) | Out-Null
$fp = Get-Fingerprint
Set-Content -Path $FpFile -Value $fp -Encoding ASCII
Write-Output "mailbox_bus_loop init fp=$fp interval=${IntervalSec}s autoExec=$(-not $NoAutoExec)"

while ($true) {
  Start-Sleep -Seconds $IntervalSec
  $n = Get-Fingerprint
  $o = (Get-Content -Raw -ErrorAction SilentlyContinue $FpFile)
  if ($o) { $o = $o.Trim() }
  if ($n -and $n -ne $o) {
    Set-Content -Path $FpFile -Value $n -Encoding ASCII
    Handle-Tick "fingerprint_changed" -AllowDuplicate
    $pendingHostElapsed = 0
    continue
  }
  $c = Read-Current
  $needHost = $c -and ([string]$c.owner -eq "host")
  if ($needHost) {
    $pendingHostElapsed += $IntervalSec
    if ($pendingHostElapsed -ge $PendingHostHeartbeatSec) {
      $pendingHostElapsed = 0
      Handle-Tick "pending_host_task"
    }
  } else {
    $pendingHostElapsed = 0
  }
}
