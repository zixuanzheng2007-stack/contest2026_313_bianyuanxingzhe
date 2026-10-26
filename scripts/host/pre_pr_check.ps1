# PR 前必跑：同步 upstream、检测 merge 冲突、预览 gh PR 状态
param(
  [string]$Base = "dev-ai-contest-2026",
  [string]$Branch = "",
  [switch]$Fix
)
$ErrorActionPreference = "Stop"
$Root = (git rev-parse --show-toplevel).Trim()
if (-not $Branch) { $Branch = (git rev-parse --abbrev-ref HEAD).Trim() }

Write-Host "== pre_pr_check ==" -ForegroundColor Cyan
Write-Host "repo:  $Root"
Write-Host "branch: $Branch -> upstream/${Base}"

$ErrorActionPreference = "Continue"
& git -C $Root fetch upstream $Base 2>&1 | Out-Null
& git -C $Root fetch origin $Branch 2>&1 | Out-Null
$ErrorActionPreference = "Stop"

$dirty = git -C $Root status --porcelain | Where-Object { $_ -notmatch '^\?\?' }
if ($dirty) {
  Write-Host "FAIL: tracked files modified/staged. Commit or stash first." -ForegroundColor Red
  $dirty
  exit 2
}

$mergeBase = git -C $Root merge-base HEAD "upstream/$Base"
$conflicts = git -C $Root merge-tree $mergeBase HEAD "upstream/$Base" 2>&1
if ($conflicts -match "changed in both") {
  Write-Host "FAIL: merge conflicts with upstream/${Base}" -ForegroundColor Red
  $conflicts | Select-String "changed in both|CONFLICT" | Select-Object -First 30
  if ($Fix) {
    Write-Host "Run: git merge upstream/${Base}  (then resolve, commit, push)" -ForegroundColor Yellow
  }
  exit 1
}

Write-Host "OK: no merge conflict with upstream/${Base}" -ForegroundColor Green

$behind = [int](git -C $Root rev-list --count "HEAD..upstream/${Base}")
$ahead  = [int](git -C $Root rev-list --count "upstream/${Base}..HEAD")
Write-Host "ahead of upstream/${Base}: $ahead commits"
Write-Host "behind upstream/${Base}: $behind commits"

if (Get-Command gh -ErrorAction SilentlyContinue) {
  $pr = gh pr list --repo open-vela/contest2026_313_bianyuanxingzhe `
    --head "zixuanzheng2007-stack:$Branch" --state open --json number,mergeable,mergeStateStatus,url 2>$null
  if ($pr -and $pr -ne "[]") {
    $pr | ConvertFrom-Json | ForEach-Object {
      Write-Host "open PR #$($_.number): mergeable=$($_.mergeable) state=$($_.mergeStateStatus)"
      Write-Host "  $($_.url)"
    }
  } else {
    Write-Host "no open PR for branch $Branch on upstream (ok if creating new PR)"
  }
}

Write-Host "pre_pr_check passed." -ForegroundColor Green
exit 0
