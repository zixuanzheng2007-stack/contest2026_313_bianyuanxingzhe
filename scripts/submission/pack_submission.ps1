# Wrapper: Python handles Unicode paths on Windows reliably.
param(
  [string]$OutDir = "dist",
  [switch]$CheckOnly
)
$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot "pack_submission.py"
$args = @("--out-dir", $OutDir)
if ($CheckOnly) { $args += "--check-only" }
& python $py @args
exit $LASTEXITCODE
