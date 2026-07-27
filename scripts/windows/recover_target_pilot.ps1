[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$ConfirmRestart,
    [switch]$SkipCustomerAccessSimulation,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

if (-not $ConfirmRestart) {
    Write-Error 'Recovery requires -ConfirmRestart. No service was stopped or started.'
    exit 2
}

try {
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1') -ConfigPath $ConfigPath
    if ($LASTEXITCODE -ne 0) { throw "Safe stop exit code: $LASTEXITCODE" }
    & (Join-Path $PSScriptRoot 'start_target_pilot.ps1') -ConfigPath $ConfigPath -SkipCustomerAccessSimulation:$SkipCustomerAccessSimulation -NoBrowser:$NoBrowser
    if ($LASTEXITCODE -ne 0) { throw "Target-pilot startup exit code: $LASTEXITCODE" }
    Write-Host 'Target pilot recovery completed.' -ForegroundColor Green
} catch {
    Write-Error "Target pilot recovery failed: $($_.Exception.Message)"
    Write-Host 'No unknown process was force-stopped by port. Use status and the read-only diagnostic report for manual review.' -ForegroundColor Yellow
    exit 1
}
