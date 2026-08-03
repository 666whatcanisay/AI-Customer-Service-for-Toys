[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
try {
    Write-Host 'Compatibility entry: stop_ai_customer_service.ps1.' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1')
    if (-not $?) { throw 'Standard stop entry failed.' }
} catch {
    Write-Error $_
    exit 1
}
