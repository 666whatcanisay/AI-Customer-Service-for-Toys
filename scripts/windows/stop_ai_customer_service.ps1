[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    foreach ($name in @('admin-web','customer-web','rag','platform')) { Stop-ManagedService $config $name }
} catch { Write-Error $_; exit 1 }
