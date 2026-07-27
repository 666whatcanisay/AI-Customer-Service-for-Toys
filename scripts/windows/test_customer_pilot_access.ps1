[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ServerHost,
    [ValidateRange(1, 65535)]
    [int]$Port = 5173
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $result = Get-TargetPilotCustomerAccess $ServerHost $Port
    Write-Host "Customer access state: $($result.State)"
    Write-Host "Server: $($result.ServerHost):$($result.Port)"
    if ($null -ne $result.Probes) {
        Write-Host "TCP: $($result.Probes.TcpReachable); page: $($result.Probes.CustomerPage.Reachable); /rag-api: $($result.Probes.RagProxy.Reachable); /platform-api: $($result.Probes.PlatformProxy.Reachable)"
    }
    Write-Host $result.SimulationScope
    if (-not $result.Ready) {
        switch ($result.State) {
            'NETWORK_SEGMENTED' { Write-Host 'Check the controlled Private network and the scoped TCP 5173 firewall rule. Do not open 8000, 8011, or 5174.' -ForegroundColor Yellow }
            'CUSTOMER_PATH_UNAVAILABLE' { Write-Host 'Keep the server services running and ask the operator to inspect the server-side readiness report and same-origin proxies.' -ForegroundColor Yellow }
            default { Write-Host 'Only a private server IPv4 and TCP 5173 are accepted by this client check.' -ForegroundColor Yellow }
        }
        exit 2
    }
} catch {
    Write-Error 'Customer access check failed without saving customer content or response bodies.'
    exit 1
}
