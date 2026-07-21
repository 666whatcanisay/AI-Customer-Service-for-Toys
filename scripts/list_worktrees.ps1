[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not installed or is not on PATH.' }
if (-not (git rev-parse --show-toplevel 2>$null)) { throw 'Run this script from inside the intended Git repository.' }
git worktree list --porcelain
