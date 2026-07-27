[CmdletBinding()]
param(
    [string]$ConfigPath,
    [ValidateSet('A','C','B','ALL')]
    [string[]]$Component = @('ALL'),
    [switch]$ConfirmDisruption,
    [switch]$NoBrowser,
    [switch]$AllowFirewallGate
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

if (-not $ConfirmDisruption) {
    Write-Error 'Component recovery rehearsal requires -ConfirmDisruption. No service was stopped.'
    exit 2
}

$config = $null
$currentLabel = ''
try {
    $config = Resolve-LanRuntimeConfig (Get-LocalConfig $ConfigPath)
    $componentMap = [ordered]@{
        C = [pscustomobject]@{ Name='platform'; Label='C' }
        A = [pscustomobject]@{ Name='rag'; Label='A' }
        B = [pscustomobject]@{ Name='customer-web'; Label='B' }
    }
    $requested = if ($Component -contains 'ALL') { @('A','C','B') } else { @($Component | Select-Object -Unique) }
    $initial = Get-TargetPilotReadiness $config -Mode Lan
    $serviceOnlyReady = $AllowFirewallGate -and
        $initial.State -eq 'FIREWALL_CONFIGURATION_REQUIRED' -and
        $initial.NetworkReady -and
        $initial.AdminLoopback -and
        $initial.ServiceFailures.Count -eq 0 -and
        $initial.Probes.TcpReachable -and
        $initial.Probes.CustomerPage.Reachable -and
        $initial.Probes.RagProxy.Reachable -and
        $initial.Probes.PlatformProxy.Reachable
    if (-not $initial.Ready -and -not $serviceOnlyReady) {
        Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'NOT_READY' $initial @($requested)
        throw 'Initial pilot readiness is not complete; the rehearsal will not stop any service.'
    }

    foreach ($label in $requested) {
        $currentLabel = $label
        $target = $componentMap[$label]
        Write-Host "Rehearsing controlled $label stop and full managed recovery..." -ForegroundColor Yellow
        Stop-ManagedService $config $target.Name
        $stopped = Get-TargetPilotReadiness $config -Mode Lan
        if ($stopped.ServiceFailures -notcontains $label) {
            Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'FAILED' $stopped @($label)
            throw "The expected $label service outage was not observed safely."
        }
        Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'NOT_READY' $stopped @($label)

        & (Join-Path $PSScriptRoot 'recover_target_pilot.ps1') -ConfigPath $ConfigPath -ConfirmRestart -NoBrowser:$NoBrowser -AllowFirewallGate:$AllowFirewallGate
        if ($LASTEXITCODE -ne 0) { throw "Managed recovery failed after $label stop (exit code $LASTEXITCODE)." }
        $recovered = Get-TargetPilotReadiness $config -Mode Lan
        $serviceOnlyRecovered = $AllowFirewallGate -and
            $recovered.State -eq 'FIREWALL_CONFIGURATION_REQUIRED' -and
            $recovered.NetworkReady -and
            $recovered.AdminLoopback -and
            $recovered.ServiceFailures.Count -eq 0 -and
            $recovered.Probes.TcpReachable -and
            $recovered.Probes.CustomerPage.Reachable -and
            $recovered.Probes.RagProxy.Reachable -and
            $recovered.Probes.PlatformProxy.Reachable
        if (-not $recovered.Ready -and -not $serviceOnlyRecovered) {
            Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'FAILED' $recovered @($label)
            throw "$label recovery did not return the pilot to a ready state."
        }
        Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'RECOVERED' $recovered @($label)
        if ($recovered.Ready) {
            Write-Host "$label stop and managed recovery passed." -ForegroundColor Green
        } else {
            Write-Warning "$label service recovery passed, but the scoped TCP 5173 firewall gate remains unresolved."
        }
    }
} catch {
    if ($null -ne $config) { Add-TargetPilotOpsEvent $config 'COMPONENT_RECOVERY' 'FAILED' $null @($currentLabel) }
    Write-Error 'Component recovery rehearsal did not complete. Check the sanitised pilot event log and read-only LAN diagnostic; no unknown process was force-stopped.'
    exit 1
}
