# SSH 到本机 Ubuntu Guest（队友 Cursor 同机）
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemoteCommand
)
$ErrorActionPreference = "Stop"
$key = Join-Path $env:USERPROFILE ".ssh\id_ed25519_openvela_vm"
$host_addr = "a1@192.168.126.128"
$sshArgs = @("-i", $key, "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", $host_addr)
if ($RemoteCommand.Count -gt 0) {
  & ssh @sshArgs ($RemoteCommand -join " ")
} else {
  & ssh @sshArgs
}
exit $LASTEXITCODE
