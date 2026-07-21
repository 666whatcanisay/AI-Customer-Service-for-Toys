[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not installed or is not on PATH.' }
$root = (git rev-parse --show-toplevel 2>$null)
if (-not $root) { throw 'Run this script from inside the intended Git repository.' }
if ((git status --porcelain)) { throw 'Working tree has uncommitted changes. Commit or stash them before creating worktrees.' }

$parent = Split-Path $root -Parent
$items = @(
  @{ Branch = 'agent/rag-core'; Name = 'AI-CS-rag-core' },
  @{ Branch = 'agent/user-client'; Name = 'AI-CS-user-client' },
  @{ Branch = 'agent/platform-center'; Name = 'AI-CS-platform-center' }
)
foreach ($item in $items) {
  $target = Join-Path $parent $item.Name
  if (Test-Path -LiteralPath $target) { Write-Host "Skipped: $target already exists."; continue }
  git show-ref --verify --quiet "refs/heads/$($item.Branch)"
  if ($LASTEXITCODE -ne 0) { Write-Warning "Skipped: branch $($item.Branch) does not exist."; continue }
  git worktree add $target $item.Branch
  if ($LASTEXITCODE -ne 0) { throw "Failed to create $target." }
  Write-Host "Created: $target ($($item.Branch))"
}
