[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'

try {
    $arguments = @{}
    if (-not [string]::IsNullOrWhiteSpace($ConfigPath)) { $arguments.ConfigPath = $ConfigPath }
    & (Join-Path $PSScriptRoot 'stop_ai_customer_service.ps1') @arguments
    if (-not $?) { throw 'AI-CS Core lifecycle stop failed.' }
    Write-Host 'AI-CS Production Server Runtime stopped.' -ForegroundColor Green
} catch {
    Write-Error $_
    exit 1
}
