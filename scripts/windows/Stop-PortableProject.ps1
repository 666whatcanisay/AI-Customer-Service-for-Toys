[CmdletBinding()]
param([switch]$IncludeCurrentPageAgent)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$config = Join-Path $root '.runtime\phase-e\config\green-standard.local.ps1'

if ($IncludeCurrentPageAgent) {
    & (Join-Path $root 'AI-CS-Channel-Execution-Engine\scripts\windows\Stop-AiCs-CurrentPage.ps1') -AiCsRoot $root
}
if (Test-Path -LiteralPath $config -PathType Leaf) {
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1') -ConfigPath $config
}
Write-Host 'STOP_PORTABLE_PROJECT=PASS' -ForegroundColor Green
