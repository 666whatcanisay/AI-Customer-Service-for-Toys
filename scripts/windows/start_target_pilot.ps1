[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$SkipCustomerAccessSimulation,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

try {
    & (Join-Path $PSScriptRoot 'start_lan_ai_customer_service.ps1') -ConfigPath $ConfigPath -NoBrowser:$NoBrowser
    if ($LASTEXITCODE -ne 0) { throw "LAN startup exit code: $LASTEXITCODE" }
    if ($SkipCustomerAccessSimulation) {
        Write-Host 'Target pilot services started; customer-access simulation was skipped by request.' -ForegroundColor Green
        return
    }
    & (Join-Path $PSScriptRoot 'check_target_pilot_readiness.ps1') -ConfigPath $ConfigPath -Mode Lan
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Services started, but customer-access simulation did not pass. Services remain running and were not stopped automatically.'
        exit $LASTEXITCODE
    }
    Write-Host 'Target pilot started and completed the server-side access simulation. A second customer computer still needs manual acceptance.' -ForegroundColor Green
} catch {
    Write-Error "Target pilot startup failed: $($_.Exception.Message)"
    Write-Host 'No service was stopped automatically. Check LAN status first, then use the managed-PID safe stop entry only when needed.' -ForegroundColor Yellow
    exit 1
}
