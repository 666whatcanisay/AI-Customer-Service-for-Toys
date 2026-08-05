[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $baseConfig $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    Assert-AiCsGatewayProductionConfig $baseConfig | Out-Null
    $config = Resolve-AiCsGatewayNetworkConfig $baseConfig 'LAN'
    $readiness = Get-AiCsGatewayLanFirewallReadiness $config
    Write-Host "Gateway mode: LAN"
    Write-Host "Gateway endpoint: $($config.GatewayEndpointOrigin)"
    Write-Host "Allowed networks: $($config.GatewayAllowedNetworksResolved -join ',')"
    Write-Host "Rule: $($readiness.RuleName)"
    Write-Host "Required scope: enabled Private inbound Allow; TCP $($readiness.BindAddress):$($readiness.Port); remote $($readiness.AllowedNetworks -join ',')"
    Write-Host "Rule state: $($readiness.State); ready=$($readiness.Ready)"
    Write-Host 'This check is read-only. It never disables or changes Windows Firewall.'
    if (-not $readiness.Ready) { exit 2 }
} catch { Write-Error $_; exit 1 }
