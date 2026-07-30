[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$SkipCustomerAccessSimulation,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    & (Join-Path $PSScriptRoot 'start_ai_customer_service.ps1') -ConfigPath $ConfigPath -NoBrowser:$NoBrowser
    if ($LASTEXITCODE -ne 0) { throw "Standard runtime startup exit code: $LASTEXITCODE" }
    if ($SkipCustomerAccessSimulation) {
        $config = Get-LocalConfig $ConfigPath
        Add-TargetPilotOpsEvent $config 'START' 'STARTED'
        Write-Host 'Target pilot services started; customer-access simulation was skipped by request.' -ForegroundColor Green
        return
    }
    & (Join-Path $PSScriptRoot 'check_target_pilot_readiness.ps1') -ConfigPath $ConfigPath -Mode Local -EventAction START
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Services started, but customer-access simulation did not pass. Services remain running and were not stopped automatically.'
        exit $LASTEXITCODE
    }
    Write-Host 'Target pilot standard runtime started and completed the server-local access simulation.' -ForegroundColor Green
} catch {
    Write-Error 'Target pilot startup failed. No sensitive exception details were written to the pilot event log.'
    Write-Host 'The standard startup entry automatically cleans up services started by a failed partial launch. Check standard status before any retry.' -ForegroundColor Yellow
    exit 1
}
