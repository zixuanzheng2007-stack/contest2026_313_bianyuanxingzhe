# Dot-source: . "$PSScriptRoot\_env.ps1"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ArtifactsDir = Join-Path $RepoRoot 'VMware_share\artifacts'
