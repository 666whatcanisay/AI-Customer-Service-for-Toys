[CmdletBinding()]
param(
    [string]$ConfigPath,
    [ValidateSet('Auto','Local','Lan')]
    [string]$Mode = 'Auto'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsGatewayProductionConfig $baseConfig | Out-Null
    $effectiveNetworkMode = Resolve-StandardRuntimeNetworkMode $baseConfig $Mode
    $config = Resolve-AiCsGatewayNetworkConfig $baseConfig $effectiveNetworkMode

    & (Join-Path $PSScriptRoot 'status_ai_customer_service.ps1') -ConfigPath $resolvedConfigPath -Mode $Mode
    if (-not $?) { throw 'AI-CS Core lifecycle status failed.' }

    $runtimeConsole = Get-AiCsServerRuntimeConsole $config
    $gatewayHealth = Get-AiCsGatewayRuntimeHealth $config
    Write-Host '--- Production Server Runtime ---' -ForegroundColor Cyan
    Write-Host "Server: $($runtimeConsole.server.status); version=$($runtimeConsole.server.version); runtimeMode=$($runtimeConsole.server.runtime_mode); networkMode=$($runtimeConsole.server.network_mode)"
    Write-Host "Gateway: $($gatewayHealth.status); version=$($gatewayHealth.version); contract=$($gatewayHealth.contract_version); configured=$($runtimeConsole.gateway.configuration_state)"
    if ($effectiveNetworkMode -eq 'LAN') {
        $edgeStatus = Get-AiCsGatewayLanServiceStatus $config
        $firewall = Get-AiCsGatewayLanFirewallReadiness $config
        Write-Host "Gateway LAN edge: $($edgeStatus.State); listener=$($config.GatewayLanBindAddressResolved):$($config.GatewayLanPort); allowed=$($config.GatewayAllowedNetworksResolved -join ',')"
        Write-Host "Gateway LAN firewall: $($firewall.State); ready=$($firewall.Ready); rule=$($firewall.RuleName)"
    } else {
        Write-Host "Gateway LOCAL endpoint: $($config.GatewayEndpointOrigin); A Core remains loopback-only."
    }
    Write-Host "Operations Console: $($config.AdminWebUrl)"
} catch {
    Write-Error $_
    exit 1
}
