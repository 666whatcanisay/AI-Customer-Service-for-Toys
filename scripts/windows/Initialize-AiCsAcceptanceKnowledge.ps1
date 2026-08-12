[CmdletBinding()]
param([Parameter(Mandatory)] [string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
$config = Get-LocalConfig $ConfigPath

if ([string]$config.RuntimeMode -notin @('shadow','recovery')) {
    throw 'Acceptance knowledge initialization is limited to shadow/recovery Runtime.'
}
if ([string]::IsNullOrWhiteSpace([string]$config.TestKnowledgePackageId)) {
    throw 'Acceptance initialization requires an explicit TestKnowledgePackageId.'
}
if (-not [bool]$config.AutoImportTestData -and -not [bool]$config.AutoSyncTestKnowledge) {
    throw 'No acceptance knowledge initialization action is enabled.'
}
Assert-PlatformDatabaseReady $config
if ([bool]$config.AutoImportTestData) { Import-TestDataPackage $config | Out-Null }
if ([bool]$config.AutoSyncTestKnowledge) { Sync-TestKnowledge $config | Out-Null }
Write-Host 'Acceptance knowledge initialization PASS. Production startup was not used.' -ForegroundColor Green
