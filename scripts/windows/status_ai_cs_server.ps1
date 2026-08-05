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
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsGatewayProductionConfig $config | Out-Null

    & (Join-Path $PSScriptRoot 'status_ai_customer_service.ps1') -ConfigPath $resolvedConfigPath -Mode $Mode
    if (-not $?) { throw 'AI-CS Core lifecycle status failed.' }

    $runtimeConsole = Get-AiCsServerRuntimeConsole $config
    $gatewayHealth = Get-AiCsGatewayRuntimeHealth $config
    Write-Host '--- Production Server Runtime ---' -ForegroundColor Cyan
    Write-Host "Server: $($runtimeConsole.server.status); version=$($runtimeConsole.server.version); runtimeMode=$($runtimeConsole.server.runtime_mode)"
    Write-Host "Gateway: $($gatewayHealth.status); version=$($gatewayHealth.version); contract=$($gatewayHealth.contract_version); configured=$($runtimeConsole.gateway.configuration_state)"
    Write-Host "Operations Console: $($config.AdminWebUrl)"
} catch {
    Write-Error $_
    exit 1
}
