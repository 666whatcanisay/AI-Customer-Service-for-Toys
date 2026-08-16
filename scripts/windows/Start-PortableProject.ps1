[CmdletBinding()]
param([switch]$NoBrowser, [switch]$IncludeCurrentPageAgent)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$config = Join-Path $root '.runtime\phase-e\config\green-standard.local.ps1'
& (Join-Path $PSScriptRoot 'Doctor-PortableProject.ps1') -RequireRuntime
if ($LASTEXITCODE -ne 0) { throw 'Run Bootstrap-PortableProject.ps1 first.' }

& (Join-Path $PSScriptRoot 'start_ai_customer_service.ps1') -ConfigPath $config -Mode Local -NoBrowser:$NoBrowser
if ($LASTEXITCODE -ne 0) { throw 'AI-CS startup failed.' }

if ($IncludeCurrentPageAgent) {
    $engineStart = Join-Path $root 'AI-CS-Channel-Execution-Engine\scripts\windows\Start-AiCs-CurrentPage.ps1'
    & $engineStart
    if ($LASTEXITCODE -ne 0) { throw 'Current-page Channel Agent startup failed.' }
}

Write-Host 'START_PORTABLE_PROJECT=PASS' -ForegroundColor Green
