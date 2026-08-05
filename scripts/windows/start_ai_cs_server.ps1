[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$NoBrowser,
    [ValidateSet('Auto','Local','Lan')]
    [string]$Mode = 'Auto',
    [ValidateRange(1, 600)]
    [int]$GatewayTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsGatewayProductionConfig $baseConfig | Out-Null
    $effectiveNetworkMode = Resolve-StandardRuntimeNetworkMode $baseConfig $Mode
    $config = Resolve-AiCsGatewayNetworkConfig $baseConfig $effectiveNetworkMode
    $gatewayLanRecordPath = Get-ServiceRecordPath $baseConfig 'gateway-lan'
    if ($effectiveNetworkMode -eq 'LAN') {
        $firewall = Assert-AiCsGatewayLanFirewallReady $config
        $gatewayAllowedNetworkText = @($config.GatewayAllowedNetworksResolved) -join ','
        Write-Host "Gateway LAN preflight: bind=$($config.GatewayLanBindAddressResolved):$($config.GatewayLanPort); allowed=$gatewayAllowedNetworkText; firewall=$($firewall.State)" -ForegroundColor Cyan
    } elseif (Test-Path -LiteralPath $gatewayLanRecordPath -PathType Leaf) {
        throw 'LOCAL mode found a gateway-lan record. Run stop_ai_cs_server.ps1 before changing network modes.'
    }

    & (Join-Path $PSScriptRoot 'start_ai_customer_service.ps1') -ConfigPath $resolvedConfigPath -NoBrowser:$NoBrowser -Mode $Mode
    if (-not $?) { throw 'AI-CS Core lifecycle start failed.' }

    if ($effectiveNetworkMode -eq 'LAN') {
        Start-AiCsGatewayLanService $config
    }

    $gatewayHealth = Wait-AiCsGatewayRuntimeReady $config $GatewayTimeoutSeconds
    $runtimeConsole = Get-AiCsServerRuntimeConsole $config
    Write-Host 'AI-CS Production Server Runtime started.' -ForegroundColor Green
    Write-Host "Server: $($runtimeConsole.server.status); version=$($runtimeConsole.server.version); runtimeMode=$($runtimeConsole.server.runtime_mode); networkMode=$($runtimeConsole.server.network_mode)"
    Write-Host "Gateway: $($gatewayHealth.status); version=$($gatewayHealth.version); contract=$($gatewayHealth.contract_version)"
    Write-Host "Gateway endpoint: $($config.GatewayEndpointOrigin); mode=$effectiveNetworkMode"
    Write-Host "Operations Console: $($config.AdminWebUrl)"
} catch {
    Write-Error $_
    exit 1
}
