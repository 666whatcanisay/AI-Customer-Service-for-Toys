[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    Stop-ManagedService $config 'gateway-lan'
    $arguments = @{}
    if (-not [string]::IsNullOrWhiteSpace($resolvedConfigPath)) { $arguments.ConfigPath = $resolvedConfigPath }
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1') @arguments
    if (-not $?) { throw 'AI-CS Core lifecycle stop failed.' }
    Write-Host 'AI-CS Production Server Runtime stopped.' -ForegroundColor Green
} catch {
    Write-Error $_
    exit 1
}
