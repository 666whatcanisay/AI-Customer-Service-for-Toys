[CmdletBinding()]
param(
    [string]$ConfigPath,
    [ValidateSet('Lan','Local')]
    [string]$Mode = 'Lan',
    [switch]$NoRecord
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $baseConfig = Get-LocalConfig $ConfigPath
    $config = if ($Mode -eq 'Lan') { Resolve-LanRuntimeConfig $baseConfig } else { $baseConfig }
    $readiness = Get-TargetPilotReadiness $config -Mode $Mode
    $reportPath = if ($NoRecord) { '' } else { Save-TargetPilotReadinessReport $config $readiness }
    Write-TargetPilotReadiness $readiness $reportPath
    if (-not $readiness.Ready) { exit 2 }
} catch {
    Write-Error "Target pilot readiness check failed: $($_.Exception.Message)"
    Write-Host 'Recovery: check status, run the read-only LAN diagnostic, then use safe stop and restart only after record verification.' -ForegroundColor Yellow
    exit 1
}
