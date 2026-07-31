[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [string]$ExpectedRevision = "0012_internal_production_finalization_v1",

    [switch]$Compact
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = Join-Path $repoRoot "platform_backend\.venv\Scripts\python.exe"
$checkerPath = Join-Path $PSScriptRoot "database_health_check.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "未找到C Platform Backend Python环境：$pythonPath"
}

$arguments = @($checkerPath, $DatabasePath, "--expected-revision", $ExpectedRevision)
if ($Compact) {
    $arguments += "--compact"
}

& $pythonPath @arguments
exit $LASTEXITCODE
