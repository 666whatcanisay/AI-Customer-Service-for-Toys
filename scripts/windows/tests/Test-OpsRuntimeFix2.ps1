Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-runtime-fix2-' + [Guid]::NewGuid().ToString('N'))

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
    } catch {
        return
    }
    throw "$Label should fail but did not."
}

try {
    foreach ($path in @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\status_ai_customer_service.ps1',
        'scripts\windows\stop_ai_customer_service.ps1',
        'scripts\windows\config.local.ps1.example'
    )) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $repositoryRoot $path),
            [ref]$tokens,
            [ref]$errors
        )
        if ($errors.Count -gt 0) { throw "$path has a PowerShell syntax error: $($errors[0].Message)" }
    }

    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $temporaryRepository = Join-Path $temporaryRoot 'repository'
    New-Item -ItemType Directory -Force -Path @(
        (Join-Path $temporaryRepository 'backend'),
        (Join-Path $temporaryRepository 'frontend'),
        (Join-Path $temporaryRepository 'platform_backend')
    ) | Out-Null
    $ragPython = Join-Path $temporaryRepository 'rag.exe'
    $platformPython = Join-Path $temporaryRepository 'platform.exe'
    New-Item -ItemType File -Path $ragPython, $platformPython | Out-Null
    $internalSecretPath = Join-Path $temporaryRoot 'runtime\secrets\internal-service.secret'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $internalSecretPath) | Out-Null
    [IO.File]::WriteAllText($internalSecretPath, ('i' * 32), [Text.UTF8Encoding]::new($false))
    $legacyConfigPath = Join-Path $temporaryRoot 'legacy-config.ps1'
    @"
@{
    RepositoryRoot = '$temporaryRepository'
    RagPythonPath = '$ragPython'
    PlatformPythonPath = '$platformPython'
    PnpmCommand = '$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe'
    RagPort = 18000
    CustomerWebPort = 15173
    PlatformPort = 18011
    BindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:15173/'
    RagHealthPath = '/api/health'
    PlatformHealthPath = '/health'
    OllamaModel = 'qwen3.5:9b'
    CorsAllowedOrigins = @('http://127.0.0.1:15173')
    OpenBrowser = (1 -eq 0)
    RuntimeDirectory = '$temporaryRoot\runtime'
    InternalServiceSecretReference = '$internalSecretPath'
    TestDataPackagePath = ''
    AutoImportTestData = (1 -eq 0)
}
"@ | Set-Content -LiteralPath $legacyConfigPath -Encoding UTF8

    $config = Get-LocalConfig $legacyConfigPath
    if (
        $config.OllamaBaseUrl -ne 'http://127.0.0.1:11434' -or
        $config.PlatformDatabaseUrl -ne 'sqlite:///./platform.db' -or
        $config.TestKnowledgePackageId -ne 'PDD-SM-2026-001-TEST' -or
        -not $config.AutoSyncTestKnowledge -or
        $config.RagPrimaryCollectionName -ne 'documents' -or
        $config.RagActiveCollectionName -ne 'test_knowledge_v031' -or
        $config.RagVectorDbPath -ne (Join-Path $temporaryRepository 'backend\vector_db')
    ) {
        throw 'Legacy config did not receive the required optional defaults.'
    }

    $platformEnvironment = Get-LocalPlatformEnvironment $config
    if ($platformEnvironment.AI_SERVICE_BASE_URL -ne 'http://127.0.0.1:18000') {
        throw 'C runtime did not receive the active A runtime address.'
    }
    $adminEnvironment = Get-AdminWebEnvironment $config
    if (
        $adminEnvironment.VITE_AI_API_BASE_URL -ne 'http://127.0.0.1:18000' -or
        $adminEnvironment.VITE_PLATFORM_API_BASE_URL -ne 'http://127.0.0.1:18011'
    ) {
        throw 'Admin runtime did not receive the configured A/C target ports.'
    }

    New-Item -ItemType Directory -Force -Path $config.RuntimeDirectory | Out-Null
    [ordered]@{
        packageId = $config.TestKnowledgePackageId
        syncedItems = 47
        collectionCount = 47
        verifiedUtc = '2026-07-27T00:00:00.0000000Z'
    } | ConvertTo-Json | Set-Content -LiteralPath (Get-TestKnowledgeSyncRecordPath $config) -Encoding UTF8
    $syncHistory = Get-TestKnowledgeSyncHistory $config
    if ($syncHistory.State -ne 'HISTORICAL_SYNC' -or $syncHistory.CollectionCount -ne 47) {
        throw 'Test knowledge history did not retain its historical count.'
    }

    function Get-Json([string]$Url, [string]$Label) {
        if ($Url -like '*/api/knowledge/statistics') {
            return [pscustomobject]@{
                data = [pscustomobject]@{
                    document_count = 0
                    chunk_count = 0
                    collection_name = 'test_knowledge_v031'
                    primary_collection_name = 'documents'
                    active_collection_name = 'test_knowledge_v031'
                    active_collection_chunk_count = 0
                    active_collection_available = $true
                    available_collections = @(
                        [pscustomobject]@{ name='documents'; chunk_count=0 },
                        [pscustomobject]@{ name='test_knowledge_v031'; chunk_count=0 }
                    )
                    vector_database = 'ChromaDB'
                }
            }
        }
        return [pscustomobject]@{ ready=$true; model_configured=$true; initialization_error=$null }
    }
    $runtimeStatistics = Get-RagKnowledgeRuntimeStatistics $config
    if ($runtimeStatistics.State -ne 'AVAILABLE' -or $runtimeStatistics.ActiveCollectionChunkCount -ne 0 -or $runtimeStatistics.ActiveCollectionName -ne 'test_knowledge_v031') {
        throw 'Runtime knowledge statistics were not read from the live statistics response.'
    }
    if ((Get-TestKnowledgeRuntimeConsistency $syncHistory $runtimeStatistics $config.RagActiveCollectionName) -ne 'MISMATCH') {
        throw 'Historical sync and runtime statistics mismatch was not detected.'
    }
    $emptyCollectionState = Get-RagActiveCollectionStartupState $config
    if ($emptyCollectionState.Ready -or $emptyCollectionState.Reason -ne 'ACTIVE_COLLECTION_EMPTY') {
        throw 'An empty active collection was not downgraded to a startup warning.'
    }
    Remove-Item -LiteralPath Function:\Get-Json -Force

    function Get-Json([string]$Url, [string]$Label) {
        if ($Url -like '*/api/knowledge/statistics') {
            return [pscustomobject]@{
                data = [pscustomobject]@{
                    document_count = 0
                    chunk_count = 47
                    collection_name = 'test_knowledge_v031'
                    primary_collection_name = 'documents'
                    active_collection_name = 'test_knowledge_v031'
                    active_collection_chunk_count = 47
                    active_collection_available = $true
                    available_collections = @(
                        [pscustomobject]@{ name='documents'; chunk_count=0 },
                        [pscustomobject]@{ name='test_knowledge_v031'; chunk_count=47 }
                    )
                    vector_database = 'ChromaDB'
                }
            }
        }
        return [pscustomobject]@{ ready=$true; model_configured=$true; initialization_error=$null }
    }
    $readyCollectionState = Get-RagActiveCollectionStartupState $config
    if (-not $readyCollectionState.Ready -or $readyCollectionState.Statistics.ActiveCollectionChunkCount -ne 47) {
        throw 'A populated configured active collection did not pass the startup check.'
    }
    Remove-Item -LiteralPath Function:\Get-Json -Force

    function Get-Json([string]$Url, [string]$Label) { throw 'statistics endpoint unavailable' }
    $unavailableStatistics = Get-RagKnowledgeRuntimeStatistics $config
    if ($unavailableStatistics.State -ne 'UNAVAILABLE' -or (Get-TestKnowledgeRuntimeConsistency $syncHistory $unavailableStatistics $config.RagActiveCollectionName) -ne 'STATISTICS_UNAVAILABLE') {
        throw 'Unavailable runtime statistics were not represented explicitly.'
    }
    Remove-Item -LiteralPath Function:\Get-Json -Force

    $script:cleanupOrder = @()
    function Update-ManagedServiceListenerRecord($Config, [string]$Name) { throw 'No record exists in this isolated cleanup-order test.' }
    function Stop-ManagedService($Config, [string]$Name) { $script:cleanupOrder += $Name }
    $cleanupFailures = @(Stop-StartedServices $config @('platform','rag','customer-web','admin-web'))
    if ($cleanupFailures.Count -gt 0) { throw "Isolated cleanup unexpectedly failed: $($cleanupFailures -join ',')" }
    if (($script:cleanupOrder -join ',') -ne 'admin-web,customer-web,rag,platform') {
        throw "Partial-start cleanup order is unsafe: $($script:cleanupOrder -join ',')"
    }
    Remove-Item -LiteralPath Function:\Stop-ManagedService -Force
    Remove-Item -LiteralPath Function:\Update-ManagedServiceListenerRecord -Force

    $startScriptText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\start_ai_customer_service.ps1') -Raw
    $statusScriptText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\status_ai_customer_service.ps1') -Raw
    if ($startScriptText -notmatch 'Stop-StartedServices' -or $startScriptText -notmatch 'Get-RagActiveCollectionStartupState' -or $startScriptText -notmatch 'KNOWLEDGE_SYNC_NON_FATAL') {
        throw 'Standard startup does not enforce active-collection readiness and partial-start cleanup.'
    }
    if ($statusScriptText -notmatch 'A active collection' -or $statusScriptText -notmatch 'A available collections') {
        throw 'Standard status does not display active and available collection state.'
    }

    Assert-Throws { Assert-OllamaReady @{ OllamaBaseUrl='http://127.0.0.1:1'; OllamaModel='qwen3.5:9b' } | Out-Null } 'Unavailable Ollama check'
    Assert-Throws { Assert-OllamaReady @{ OllamaBaseUrl='http://127.0.0.1:11434'; OllamaModel='does-not-exist:0' } | Out-Null } 'Missing Ollama model check'

    function Get-PortOwner([int]$Port) { @(99999) }
    Assert-Throws { Assert-PortAvailable $config 'rag' $config.RagPort } 'Unknown port owner protection'
    Remove-Item -LiteralPath Function:\Get-PortOwner -Force

    function Get-Json([string]$Url, [string]$Label) {
        [pscustomobject]@{ ready=$true; model_configured=$false; initialization_error=$null }
    }
    Assert-Throws { Assert-RagRuntimeReady $config | Out-Null } 'model_configured=false protection'
    Remove-Item -LiteralPath Function:\Get-Json -Force

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $nestedZip = Join-Path $temporaryRoot 'nested.zip'
    $archive = [IO.Compression.ZipFile]::Open($nestedZip, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($entryName in @('fixture/manifest.json', 'fixture/content.txt')) {
            $entry = $archive.CreateEntry($entryName)
            $writer = New-Object IO.StreamWriter($entry.Open())
            try { $writer.Write($entryName) } finally { $writer.Dispose() }
        }
    } finally {
        $archive.Dispose()
    }
    $normalizationConfig = @{ TestDataPackagePath=$nestedZip; RuntimeDirectory=(Join-Path $temporaryRoot 'runtime') }
    $normalizedZip = Get-NormalizedTestDataPackagePath $normalizationConfig
    $normalizedArchive = [IO.Compression.ZipFile]::OpenRead($normalizedZip)
    try {
        if (-not ($normalizedArchive.Entries | Where-Object { $_.FullName -eq 'manifest.json' })) {
            throw 'Nested ZIP was not normalized to a root manifest.'
        }
    } finally {
        $normalizedArchive.Dispose()
    }

    Write-Host 'OPS-RUNTIME-FIX2 unit checks passed.'
} finally {
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd('\')) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
