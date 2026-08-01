[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
try {
    Write-Host 'Compatibility entry: status_ai_customer_service.ps1.' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'status_ai_customer_service.ps1') -Mode Auto
    if (-not $?) { throw 'Standard status entry failed.' }
} catch {
    Write-Error $_
    exit 1
}
