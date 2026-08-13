$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
. (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')

$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ("ai-cs-rag-activation-" + [Guid]::NewGuid().ToString('N'))
try {
    $runtimeRoot = Join-Path $fixtureRoot 'runtime'
    $vectorRoot = Join-Path $fixtureRoot 'vector-db'
    New-Item -ItemType Directory -Path $runtimeRoot,$vectorRoot -Force | Out-Null
    $configPath = Join-Path $fixtureRoot 'runtime.local.ps1'
    '# fixture' | Set-Content -LiteralPath $configPath -Encoding UTF8
    $recordPath = Join-Path $runtimeRoot 'rag.json'
    [ordered]@{
        listener_pid = $PID
        listener_executable_path = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
        listener_started_at = [Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().ToString('o')
        startedUtc = [Diagnostics.Process]::GetCurrentProcess().StartTime.ToUniversalTime().ToString('o')
        port = 8420
        repository_root = $repositoryRoot
        repository_git_sha = ('a' * 40)
        repository_source_fingerprint = ('b' * 64)
    } | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8

    function Get-ServiceRecordPath($Config, [string]$Name) { return $recordPath }
    function Get-RepositoryRuntimeIdentity([string]$RepositoryRoot) {
        return [pscustomobject]@{
            Available = $true
            RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
            GitSha = ('a' * 40)
            SourceState = 'CLEAN'
            SourceFingerprint = ('b' * 64)
            Reason = 'TEST'
        }
    }
    function Assert-RagRuntimeReady($Config) {
        return [pscustomobject]@{ ready=$true; model_configured=$true; initialization_error=$null }
    }
    function Get-RagKnowledgeRuntimeStatistics($Config) {
        return [pscustomobject]@{
            State='AVAILABLE'
            ActiveCollectionName=[string]$Config.RagActiveCollectionName
            ActiveCollectionChunkCount=74
        }
    }

    $config = @{
        RepositoryRoot = $repositoryRoot
        RuntimeDirectory = $runtimeRoot
        RagVectorDbPath = $vectorRoot
        RagActiveCollectionName = 'test_knowledge_v031'
        OllamaModel = 'qwen3.5:9b'
    }
    $path = Write-Rc5RuntimeActivationManifest $config 'rag' $configPath
    $manifest = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.component -ne 'AI_CS_RAG' -or $manifest.activation_kind -ne 'RAG') { throw 'RAG activation identity missing.' }
    if ($manifest.source_revision -ne ('a' * 40) -or $manifest.source_fingerprint -ne ('b' * 64)) { throw 'RAG source identity missing.' }
    if ($manifest.rag_identity.model -ne 'qwen3.5:9b' -or $manifest.rag_identity.active_collection_name -ne 'test_knowledge_v031') { throw 'RAG configuration identity missing.' }
    if (-not $manifest.rag_identity.ready -or -not $manifest.rag_identity.model_configured) { throw 'RAG readiness missing.' }
    if ([bool]$manifest.diagnostics.chunk_count_is_identity) { throw 'Chunk count must remain diagnostic only.' }
    if ($manifest.PSObject.Properties.Name -contains 'canonical_database_path') { throw 'RAG activation must not pretend to own a relational database.' }

    $startText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\start_ai_customer_service.ps1') -Raw -Encoding UTF8
    if ($startText -notmatch 'Write-Rc5RuntimeActivationManifest \$config ''rag''') { throw 'Standard startup does not write the RAG activation.' }
    Write-Host 'RC5 RAG runtime activation manifest tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}
