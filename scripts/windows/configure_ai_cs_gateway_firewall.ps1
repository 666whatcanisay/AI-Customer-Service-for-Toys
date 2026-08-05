[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    if (-not (Test-AICustomerServiceAdministrator)) { throw 'Administrator rights are required. Run this script as Administrator.' }
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $baseConfig $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    Assert-AiCsGatewayProductionConfig $baseConfig | Out-Null
    $config = Resolve-AiCsGatewayNetworkConfig $baseConfig 'LAN'
    $ruleName = Get-AiCsGatewayFirewallRuleName $config
    Write-Host "This will create/update exactly one Private inbound rule: $ruleName"
    Write-Host "TCP local $($config.GatewayLanBindAddressResolved):$($config.GatewayLanPort); remote $($config.GatewayAllowedNetworksResolved -join ',')"
    Write-Host 'It will not expose 8000, 8011 or 5174, disable Windows Firewall, or change the network profile.'
    if ((Read-Host 'Type CONFIGURE to continue') -cne 'CONFIGURE') { throw 'Explicit confirmation was not received. No firewall rule was changed.' }
    $existing = @(Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) { $existing | Remove-NetFirewallRule -Confirm:$false }
    New-NetFirewallRule -DisplayName $ruleName -Description 'AI-CS controlled Gateway LAN edge; exact private address, port and client subnet only.' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $config.GatewayLanBindAddressResolved -LocalPort $config.GatewayLanPort -RemoteAddress $config.GatewayAllowedNetworksResolved -Profile Private -Enabled True | Out-Null
    $readiness = Get-AiCsGatewayLanFirewallReadiness $config
    if (-not $readiness.Ready) { throw "Firewall rule was created but validation failed: $($readiness.State)" }
    Write-Host 'Gateway LAN firewall rule configured and validated.' -ForegroundColor Green
} catch { Write-Error $_; exit 1 }
