[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $baseConfig $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    $config = Resolve-LanRuntimeConfig $baseConfig $null $null -SkipPublicNetworkGuard
    $rules = @(Get-AICustomerFirewallRules)
    Write-Host "Rule name: $(Get-AICustomerFirewallRuleName)"
    Write-Host "Customer URL: $($config.CustomerWebUrl)"
    Write-Host "Expected scope: Private, TCP 5173, remote subnet $($config.LanSubnet)"
    if ($rules.Count -eq 0) { Write-Host 'Rule state: not configured.'; exit 0 }
    foreach ($rule in $rules) {
        $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
        Write-Host "Rule state: enabled=$($rule.Enabled); direction=$($rule.Direction); action=$($rule.Action); profile=$($rule.Profile); localPort=$($port.LocalPort); remoteAddress=$($address.RemoteAddress)"
    }
} catch { Write-Error $_; exit 1 }
