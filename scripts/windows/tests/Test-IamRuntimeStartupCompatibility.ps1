$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$commonPath = Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1'
$mainPath = Join-Path $repositoryRoot 'platform_backend\app\main.py'

$common = Get-Content -Raw -LiteralPath $commonPath
$main = Get-Content -Raw -LiteralPath $mainPath
$getPackageBlock = [regex]::Match(
    $common, 'function Get-TestDataPackage[\s\S]*?(?=function Import-TestDataPackage)'
).Value
$chatSmokeBlock = [regex]::Match(
    $common, 'function Invoke-RagChatSmoke[\s\S]*$'
).Value

if ([string]::IsNullOrWhiteSpace($getPackageBlock) -or $getPackageBlock -match '/api/v1/test-data-packages') {
    throw 'Runtime startup still depends on the authenticated test-data package list.'
}
if ($common -notmatch '/api/v1/test-knowledge-packages/\$packageId/rag-export') {
    throw 'Runtime startup does not use the frozen loopback-only knowledge export.'
}
if ([string]::IsNullOrWhiteSpace($chatSmokeBlock) -or $chatSmokeBlock -match '/api/v1/test-catalog/stores') {
    throw 'RAG chat smoke still depends on the authenticated test catalog.'
}
if ($main -notmatch 'include_router\(test_catalog_router, dependencies=operations_dependencies\)') {
    throw 'Browser-facing test catalog is not protected by operations authorization.'
}
if ($main -notmatch 'include_router\(test_knowledge_internal_router\)') {
    throw 'Frozen loopback knowledge export is not separately registered.'
}

Write-Host 'PASS: IAM runtime startup uses only the frozen loopback knowledge projection and keeps browser management authenticated.' -ForegroundColor Green
