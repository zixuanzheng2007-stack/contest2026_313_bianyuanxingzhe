#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][string]$LocalAddress,
  [Parameter(Mandatory=$true)][string]$PhoneAddress,
  [ValidateRange(1024,65535)][int]$Port=8768,
  [ValidateRange(1,120)][int]$Minutes=60,
  [ValidatePattern('^Codex-EdgeWalker-Phone-Prototype(?:-[A-Za-z0-9-]{1,40})?$')]
  [string]$RuleName='Codex-EdgeWalker-Phone-Prototype'
)
$ErrorActionPreference='Stop'
foreach($address in @($LocalAddress,$PhoneAddress)) {
  $parsed=[System.Net.IPAddress]::Parse($address)
  if($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
     $address -eq '0.0.0.0' -or [System.Net.IPAddress]::IsLoopback($parsed)) {
    throw 'Explicit non-loopback IPv4 addresses are required.'
  }
}
$ruleName=$RuleName
if(Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
  throw 'An existing prototype rule must be reviewed before creating another.'
}
$pythonPath='D:\anaconda3\python.exe'
if(-not (Test-Path -LiteralPath $pythonPath)) { throw 'Expected Python runtime missing.' }
New-NetFirewallRule -Name $ruleName -DisplayName 'Edge Walker phone prototype (temporary)' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $LocalAddress `
  -RemoteAddress $PhoneAddress -LocalPort $Port -Program $pythonPath `
  -Profile Any -EdgeTraversalPolicy Block | Out-Null
try {
  $expires=(Get-Date).AddMinutes($Minutes)
  while((Get-Date) -lt $expires) { Start-Sleep -Seconds 30 }
} finally {
  Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
}
