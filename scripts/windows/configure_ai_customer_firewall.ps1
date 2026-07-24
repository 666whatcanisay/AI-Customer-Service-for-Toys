[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    if (-not (Test-AICustomerServiceAdministrator)) { throw 'Administrator rights are required. Run the firewall configuration batch file as Administrator.' }
    $config = Resolve-LanRuntimeConfig (Get-LocalConfig $ConfigPath)
    if ([int]$config.CustomerWebPort -ne 5173) { throw "This safety tool only opens TCP 5173; CustomerWebPort is $($config.CustomerWebPort). No firewall rule was changed." }
    Write-Host "This will create/update exactly one Private inbound rule: TCP 5173, remote subnet $($config.LanSubnet)."
    Write-Host 'It will not open 8000 or 8011, disable the firewall, or change VPN/network settings.'
    if ((Read-Host 'Type CONFIGURE to continue') -cne 'CONFIGURE') { throw 'Explicit confirmation was not received. No firewall rule was changed.' }
    $existingRules = @(Get-AICustomerFirewallRules)
    if ($existingRules.Count -gt 0) { $existingRules | Remove-NetFirewallRule -Confirm:$false }
    New-NetFirewallRule -DisplayName (Get-AICustomerFirewallRuleName) -Description 'AI customer service LAN entry: Private TCP 5173 only, limited to the current physical adapter subnet.' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5173 -RemoteAddress $config.LanSubnet -Profile Private -Enabled True | Out-Null
    Write-Host 'Firewall rule configured.' -ForegroundColor Green
} catch { Write-Error $_; exit 1 }
