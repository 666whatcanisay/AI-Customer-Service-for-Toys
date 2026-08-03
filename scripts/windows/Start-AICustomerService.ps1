[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
try {
    Write-Host 'Compatibility entry: start_ai_customer_service.ps1.' -ForegroundColor Yellow
    if ($DryRun) {
        . (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
        $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath ''
        $config = Get-LocalConfig $resolvedConfigPath
        Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot
        Assert-RagVirtualEnvironment $config
        Assert-Dependencies $config
        Assert-AdminWebDependencies $config | Out-Null
        Write-AiCsStartupPreflight $config $resolvedConfigPath
        Write-Host 'DryRun preflight passed; no service was started or stopped.' -ForegroundColor Green
        return
    }
    & (Join-Path $PSScriptRoot 'start_ai_customer_service.ps1') -NoBrowser:$NoBrowser -Mode Auto
    if (-not $?) { throw 'Standard start entry failed.' }
} catch {
    Write-Error $_
    exit 1
}
