$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try { $config = Get-LocalConfig; foreach ($name in @('customer-web','rag','platform')) { Stop-ManagedService $config $name } } catch { Write-Error $_; exit 1 }
