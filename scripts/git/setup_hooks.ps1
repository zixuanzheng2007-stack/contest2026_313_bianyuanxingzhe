# One-time: enable pre-push rebase hook (Windows)
$Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $Root

git config core.hooksPath .githooks
Write-Host "OK: core.hooksPath=.githooks"
Write-Host "Pre-push: scripts/git/pre_push_rebase.sh"
Write-Host "Cursor: .cursor/hooks.json (beforeShellExecution on git push)"
