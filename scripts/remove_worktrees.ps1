[CmdletBinding()]
param([switch]$ConfirmRemoval)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmRemoval) {
  Write-Host 'Dry run only. Re-run with -ConfirmRemoval to remove the three managed worktrees.'
  git worktree list
  exit 0
}
if (-not (git rev-parse --show-toplevel 2>$null)) { throw 'Run this script from inside the intended Git repository.' }
$root = git rev-parse --show-toplevel
$parent = Split-Path $root -Parent
foreach ($name in 'AI-CS-rag-core', 'AI-CS-user-client', 'AI-CS-platform-center') {
  $target = Join-Path $parent $name
  if (Test-Path -LiteralPath $target) {
    git worktree remove $target
    if ($LASTEXITCODE -ne 0) { throw "Failed to remove $target. Resolve changes manually; this script never uses force." }
    Write-Host "Removed: $target"
  }
}
