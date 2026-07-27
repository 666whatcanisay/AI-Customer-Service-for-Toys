[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try { $config = Get-LocalConfig $ConfigPath; foreach ($name in @('admin-web','customer-web','rag','platform')) { Stop-ManagedService $config $name } } catch { Write-Error $_; exit 1 }
