[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$ConfirmRestart,
    [switch]$SkipCustomerAccessSimulation,
    [switch]$NoBrowser,
    [switch]$AllowFirewallGate
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

if (-not $ConfirmRestart) {
    Write-Error 'Recovery requires -ConfirmRestart. No service was stopped or started.'
    exit 2
}

try {
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1') -ConfigPath $ConfigPath
    if ($LASTEXITCODE -ne 0) { throw "Safe stop exit code: $LASTEXITCODE" }
    $skipStartupSimulation = [bool]$SkipCustomerAccessSimulation -or [bool]$AllowFirewallGate
    & (Join-Path $PSScriptRoot 'start_target_pilot.ps1') -ConfigPath $ConfigPath -SkipCustomerAccessSimulation:$skipStartupSimulation -NoBrowser:$NoBrowser
    if ($LASTEXITCODE -ne 0) { throw "Target-pilot startup exit code: $LASTEXITCODE" }
    & (Join-Path $PSScriptRoot 'check_target_pilot_readiness.ps1') -ConfigPath $ConfigPath -Mode Lan -EventAction RECOVERY
    if ($LASTEXITCODE -ne 0) {
        $config = Resolve-LanRuntimeConfig (Get-LocalConfig $ConfigPath)
        $readiness = Get-TargetPilotReadiness $config -Mode Lan
        $serviceOnlyRecovered = $AllowFirewallGate -and
            $readiness.State -eq 'FIREWALL_CONFIGURATION_REQUIRED' -and
            $readiness.NetworkReady -and
            $readiness.AdminLoopback -and
            $readiness.ServiceFailures.Count -eq 0 -and
            $readiness.Probes.TcpReachable -and
            $readiness.Probes.CustomerPage.Reachable -and
            $readiness.Probes.RagProxy.Reachable -and
            $readiness.Probes.PlatformProxy.Reachable
        if (-not $serviceOnlyRecovered) { throw "Target-pilot recovery verification exit code: $LASTEXITCODE" }
        Add-TargetPilotOpsEvent $config 'RECOVERY' 'NOT_READY' $readiness
        Write-Warning 'Managed services recovered, but the pilot remains blocked on the scoped TCP 5173 firewall gate.'
        return
    }
    Write-Host 'Target pilot recovery completed.' -ForegroundColor Green
} catch {
    Write-Error 'Target pilot recovery failed. No sensitive exception details were written to the pilot event log.'
    Write-Host 'No unknown process was force-stopped by port. Use status and the read-only diagnostic report for manual review.' -ForegroundColor Yellow
    exit 1
}
