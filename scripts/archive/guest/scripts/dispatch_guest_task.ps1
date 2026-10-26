# 宿主机：写 TASK → 更新 CURRENT → 纸条 → SSH 启动 Guest 监听 / 触发编译
param(
  [Parameter(Mandatory = $true)]
  [string]$TaskId,
  [Parameter(Mandatory = $true)]
  [string]$Title,
  [ValidateSet("guest_build", "guest_build_wifi", "guest_compile", "guest_flash", "guest_verify", "guest_code", "none")]
  [string]$Blocker = "guest_build",
  [string]$FlashBin = "artifacts/nuttx_wifiui.bin",
  [string]$TaskBodyFile = "",
  [switch]$StartGuestLoop,
  [switch]$RunExecNow
)
$ErrorActionPreference = "Stop"
$Share = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Mail = Join-Path $Share "mailbox"
$TaskDir = Join-Path $Mail "host_to_guest"
$TaskFile = Join-Path $TaskDir "${TaskId}_$(($Title -replace '[^\w\u4e00-\u9fff]+','_')).md"
$Ssh = Join-Path $PSScriptRoot "ssh_guest.ps1"

New-Item -ItemType Directory -Force -Path $TaskDir | Out-Null

$body = if ($TaskBodyFile -and (Test-Path $TaskBodyFile)) {
  Get-Content -Raw -Encoding UTF8 $TaskBodyFile
} else {
  @"
# $TaskId · $Title

签发: Windows Host $(Get-Date -Format 'yyyy-MM-dd HH:mm')
执行: Ubuntu Guest Cursor（SSH 可达）
回执: ``mailbox/guest_to_host/REPLY_$($TaskId -replace '^TASK_','')*.md``

## 动作

见 CURRENT.json blocker=$Blocker。完成后更新 CURRENT（owner→host 若需烧录）。

## 铁律

- 不要抢 CH343 / COM7 烧录
- 不要 erase_flash / ESP BOOT
- 密码不进 git / mailbox
"@
}

Set-Content -Path $TaskFile -Value $body -Encoding UTF8

$current = @{
  ts        = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
  active_id = $TaskId
  blocker   = $Blocker
  owner     = "guest"
  guest     = @{ doing = $Title; need = "execute TASK then REPLY" }
  host      = @{ doing = "dispatched via SSH"; need = "await guest REPLY" }
  peer      = @{ doing = "idle"; need = "none" }
  do_not    = @("ESP BOOT", "guest CH343", "put wifi password in mailbox")
}
if ($Blocker -match "guest_build_wifi") {
  $current.flash = @{
    bin   = $FlashBin
    port  = "/dev/ttyACM0"
    ok    = $false
    addr  = "0x12010000"
    bytes = 0
    via   = "guest_sftool"
  }
} elseif ($Blocker -eq "guest_flash") {
  $current.flash = @{
    bin   = $FlashBin
    port  = "/dev/ttyACM0"
    ok    = $false
    addr  = "0x12010000"
    via   = "guest_sftool"
  }
} elseif ($Blocker -match "guest_build|guest_compile") {
  $current.flash = @{
    bin   = if ($FlashBin) { $FlashBin } else { "artifacts/nuttx_ai_agent.bin" }
    port  = "COM7"
    ok    = $false
    addr  = "0x12010000"
    bytes = 0
  }
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText(
  (Join-Path $Mail "CURRENT.json"),
  (($current | ConvertTo-Json -Depth 6) + "`n"),
  $utf8NoBom)

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
Set-Content -Path (Join-Path $Share "FROM_HOST_Windows.txt") -Value "$stamp $TaskId dispatched → guest ($Blocker)" -Encoding UTF8

Write-Host "WROTE $TaskFile"
Write-Host "UPDATED mailbox/CURRENT.json owner=guest blocker=$Blocker"

if ($StartGuestLoop) {
  & $Ssh "chmod +x /mnt/hgfs/VMware_share/scripts/*.sh; bash /mnt/hgfs/VMware_share/scripts/start_guest_bus_loop.sh"
}

if ($RunExecNow) {
  & $Ssh "bash /mnt/hgfs/VMware_share/scripts/mailbox_exec_guest.sh"
}

Write-Host "Guest SSH: ssh -i `$env:USERPROFILE\.ssh\id_ed25519_openvela_vm a1@192.168.126.128"
