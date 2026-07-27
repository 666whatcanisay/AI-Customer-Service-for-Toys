[CmdletBinding()]
param(
    [string]$ConfigPath,
    [ValidateSet('Lan','Local')]
    [string]$Mode = 'Lan',
    [switch]$NoRecord,
    [ValidateSet('READINESS','START','RECOVERY')]
    [string]$EventAction = 'READINESS'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $baseConfig = Get-LocalConfig $ConfigPath
    $config = if ($Mode -eq 'Lan') { Resolve-LanRuntimeConfig $baseConfig } else { $baseConfig }
    $readiness = Get-TargetPilotReadiness $config -Mode $Mode
    $reportPath = if ($NoRecord) { '' } else { Save-TargetPilotReadinessReport $config $readiness }
    Add-TargetPilotOpsEvent $config $EventAction $(if ($readiness.Ready) { 'READY' } else { 'NOT_READY' }) $readiness
    Write-TargetPilotReadiness $readiness $reportPath
    if (-not $readiness.Ready) { exit 2 }
} catch {
    Write-Error 'Target pilot readiness check failed. No sensitive exception details were written to the pilot event log.'
    Write-Host 'Recovery: check status, run the read-only LAN diagnostic, then use safe stop and restart only after record verification.' -ForegroundColor Yellow
    exit 1
}
