# 宿主机：读 CURRENT.json，执行可自动化任务（烧录等）；复杂验收只写唤醒行。
param(
  [switch]$DryRun,
  [string]$ShareRoot = ""
)
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ShareRoot)) {
  $ShareRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Mail = Join-Path $ShareRoot "mailbox"
$CurrentPath = Join-Path $Mail "CURRENT.json"
$LogPath = Join-Path $Mail "status\HOST_EXEC.log"
$Sftool = Join-Path (Split-Path $ShareRoot -Parent) "tools\sftool\sftool.exe"

function Write-ExecLog([string]$msg) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
  Write-Output $line
}

function Read-CurrentObj {
  if (-not (Test-Path -LiteralPath $CurrentPath)) { return $null }
  try {
    return Get-Content -Raw -Encoding UTF8 $CurrentPath | ConvertFrom-Json
  } catch {
    Write-ExecLog "CURRENT.json parse fail: $_"
    return $null
  }
}

function Save-CurrentObj($obj) {
  $obj.ts = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
  ($obj | ConvertTo-Json -Depth 6) + "`n" | Set-Content -Path $CurrentPath -Encoding UTF8
}

function Invoke-HostFlash($c) {
  if (-not $c.flash) {
    Write-ExecLog "flash skip: no flash block"
    return @{ ok = $false; reason = "no_flash" }
  }
  if ($c.flash.ok -eq $true) {
    Write-ExecLog "flash skip: already ok"
    return @{ ok = $true; reason = "already_ok" }
  }
  $rel = [string]$c.flash.bin
  if ([string]::IsNullOrWhiteSpace($rel)) {
    Write-ExecLog "flash fail: empty bin"
    return @{ ok = $false; reason = "empty_bin" }
  }
  $binPath = Join-Path $ShareRoot ($rel -replace '/', '\')
  if (-not (Test-Path -LiteralPath $binPath)) {
    Write-ExecLog "flash fail: missing $binPath"
    return @{ ok = $false; reason = "missing_bin"; path = $binPath }
  }
  $port = if ($c.flash.port) { [string]$c.flash.port } else { "COM7" }
  $addr = if ($c.flash.addr) { [string]$c.flash.addr } else { "0x12010000" }
  $spec = "$binPath@$addr"
  if (-not (Test-Path -LiteralPath $Sftool)) {
    Write-ExecLog "flash fail: sftool missing $Sftool"
    return @{ ok = $false; reason = "no_sftool" }
  }
  if ($DryRun) {
    Write-ExecLog "DRY flash $port $spec"
    return @{ ok = $true; reason = "dry_run" }
  }
  Write-ExecLog "flash start port=$port spec=$spec"
  & $Sftool -c SF32LB52 -p $port -b 1000000 `
    --before default_reset --after soft_reset write_flash --verify $spec 2>&1 | ForEach-Object {
    Write-ExecLog "sftool: $_"
  }
  if ($LASTEXITCODE -ne 0) {
    Write-ExecLog "flash fail exit=$LASTEXITCODE"
    return @{ ok = $false; reason = "sftool_exit"; code = $LASTEXITCODE }
  }
  Write-ExecLog "flash ok"
  return @{ ok = $true; reason = "flashed"; bin = $rel; port = $port }
}

function Write-FlashReply($c, $result) {
  $id = if ($c.active_id) { [string]$c.active_id } else { "UNKNOWN" }
  $replyDir = Join-Path $Mail "host_to_guest"
  New-Item -ItemType Directory -Force -Path $replyDir | Out-Null
  $replyPath = Join-Path $replyDir ("REPLY_{0}_FLASH.md" -f ($id -replace '^TASK_', ''))
  $res = if ($result.ok) { '**exit 0**' } else { "FAIL $($result.reason)" }
  $body = @(
    "# REPLY_${id}_FLASH · 宿主机自动烧录"
    ""
    "| 项 | 值 |"
    "|----|-----|"
    "| 时间 | $(Get-Date -Format 'yyyy-MM-dd HH:mm') |"
    "| bin | $($c.flash.bin) |"
    "| 口 | $($c.flash.port) |"
    "| 结果 | $res |"
    ""
    "自动执行: mailbox_exec_host.ps1"
  ) -join "`n"
  Set-Content -Path $replyPath -Value $body -Encoding UTF8
  Write-ExecLog "wrote $replyPath"
}

function Invoke-MailboxHostCycle {
  $c = Read-CurrentObj
  if (-not $c) {
    return @{ action = "none"; reason = "no_current" }
  }
  $owner = [string]$c.owner
  $blocker = [string]$c.blocker
  Write-ExecLog "tick owner=$owner blocker=$blocker active=$($c.active_id)"

  if ($owner -ne "host") {
    return @{ action = "idle"; owner = $owner }
  }

  # P0: 待烧录
  if ($blocker -eq "host_flash" -and $c.flash -and ($c.flash.ok -ne $true)) {
    $r = Invoke-HostFlash $c
    if ($r.ok) {
      $c.flash.ok = $true
      $c.blocker = "guest_verify"
      $c.owner = "guest"
      if (-not $c.host) { $c | Add-Member -NotePropertyName host -NotePropertyValue (@{}) }
      $c.host.doing = "auto flashed $($c.flash.bin)"
      $c.host.need = "guest verify on device"
      Save-CurrentObj $c
      Write-FlashReply $c $r
      return @{ action = "flashed"; result = $r }
    }
    return @{ action = "flash_failed"; result = $r }
  }

  # 需 Agent 目视/交互 — 只标记待唤醒
  return @{
    action = "wake_agent"
    owner  = $owner
    blocker = $blocker
    active = [string]$c.active_id
    need   = if ($c.host) { [string]$c.host.need } else { "" }
  }
}

$result = Invoke-MailboxHostCycle
$result | ConvertTo-Json -Compress | Write-Output
