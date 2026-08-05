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
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsGatewayProductionConfig $config | Out-Null

    & (Join-Path $PSScriptRoot 'start_ai_customer_service.ps1') -ConfigPath $resolvedConfigPath -NoBrowser:$NoBrowser -Mode $Mode
    if (-not $?) { throw 'AI-CS Core lifecycle start failed.' }

    $gatewayHealth = Wait-AiCsGatewayRuntimeReady $config $GatewayTimeoutSeconds
    $runtimeConsole = Get-AiCsServerRuntimeConsole $config
    Write-Host 'AI-CS Production Server Runtime started.' -ForegroundColor Green
    Write-Host "Server: $($runtimeConsole.server.status); version=$($runtimeConsole.server.version); runtimeMode=$($runtimeConsole.server.runtime_mode)"
    Write-Host "Gateway: $($gatewayHealth.status); version=$($gatewayHealth.version); contract=$($gatewayHealth.contract_version)"
    Write-Host "Operations Console: $($config.AdminWebUrl)"
} catch {
    Write-Error $_
    exit 1
}
