[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    if (-not (Test-AICustomerServiceAdministrator)) { throw 'Administrator rights are required. Run the firewall removal batch file as Administrator.' }
    $rules = @(Get-AICustomerFirewallRules)
    if ($rules.Count -eq 0) { Write-Host 'No rule created by this tool was found.'; exit 0 }
    Write-Host "This will remove exactly one fixed rule: $(Get-AICustomerFirewallRuleName)"
    if ((Read-Host 'Type REMOVE to continue') -cne 'REMOVE') { throw 'Explicit confirmation was not received. No firewall rule was removed.' }
    $rules | Remove-NetFirewallRule -Confirm:$false
    Write-Host 'Firewall rule removed.' -ForegroundColor Green
} catch { Write-Error $_; exit 1 }
