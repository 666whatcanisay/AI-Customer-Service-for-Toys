[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
$config = $null
$startedServices = @()
try {
    $config = Get-LocalConfig $ConfigPath
    Assert-RagVirtualEnvironment $config
    Assert-Dependencies $config
    Assert-AdminWebDependencies $config | Out-Null
    $services = @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort},@{Name='admin-web';Port=$config.AdminWebPort})
    Assert-ManagedRuntimeSourceConsistency $config $services
    $alreadyRunning = @($services | Where-Object { Test-ManagedServiceRunning $config $_.Name $_.Port })
    if ($alreadyRunning.Count -eq $services.Count) {
        Write-Host "AI 客服已运行：$($config.CustomerWebUrl)" -ForegroundColor Green
        Write-Host '使用检查AI客服状态.bat 查看状态，或使用停止AI客服.bat 安全停止。'
        return
    }
    if ($alreadyRunning.Count -gt 0) { throw "仅部分服务处于可信健康运行状态：$($alreadyRunning.Name -join ', ')。请先使用状态脚本核对，避免混合启动。" }
    foreach ($pair in $services) { Assert-PortAvailable $config $pair.Name $pair.Port }
    $platformEnvironment = @{ CORS_ALLOWED_ORIGINS = (@($config.CorsAllowedOrigins) -join ','); DATABASE_URL = [string]$config.PlatformDatabaseUrl; PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR = [string]$config.PlatformKnowledgeMaterialStorageDirectory }
    Invoke-WithProcessEnvironment $platformEnvironment { Invoke-PlatformMigration $config } | Out-Null

    $startedServices += 'platform'
    Start-ManagedServiceWithEnvironment $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort $platformEnvironment | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'
    Update-ManagedServiceListenerRecord $config 'platform' | Out-Null

    Import-TestDataPackage $config | Out-Null
    $ragEnvironment = Get-LocalRagEnvironment $config
    $startedServices += 'rag'
    Start-ManagedServiceWithEnvironment $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort $ragEnvironment | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    Update-ManagedServiceListenerRecord $config 'rag' | Out-Null
    Wait-RagRuntimeReady $config 120 | Out-Null
    # KNOWLEDGE_SYNC_NON_FATAL: keep the runtime available while surfacing knowledge degradation.
    try {
        Sync-TestKnowledge $config | Out-Null
    } catch {
        Write-Warning "A 知识同步异常：$($_.Exception.Message)。服务继续启动，并检查当前 active collection。"
    }
    $activeCollectionState = Get-RagActiveCollectionStartupState $config
    if ($activeCollectionState.Ready) { Invoke-RagChatSmoke $config | Out-Null }

    $vite = Join-Path $config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'
    $frontendEnvironment = Get-LocalFrontendEnvironment $config
    $startedServices += 'customer-web'
    Start-ManagedServiceWithEnvironment $config 'customer-web' (Get-Command node.exe).Source @($vite,'--host',$config.BindAddress,'--port',$config.CustomerWebPort,'--strictPort') (Join-Path $config.RepositoryRoot 'frontend') 'vite.js' $config.CustomerWebPort $frontendEnvironment | Out-Null
    Wait-HttpOk $config.CustomerWebUrl 45 '客服页面'
    Update-ManagedServiceListenerRecord $config 'customer-web' | Out-Null
    $startedServices += 'admin-web'
    Start-AdminWebService $config | Out-Null
    Write-Host "AI 客服已启动：$($config.CustomerWebUrl)" -ForegroundColor Green
    Write-Host "运营后台：$($config.AdminWebUrl)"
    Write-Host 'API 模式：DIRECT（本机排错模式）'
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    if (-not $NoBrowser -and [bool]$config.OpenBrowser) { Start-Process $config.CustomerWebUrl }
    if (-not $NoBrowser -and [bool]$config.AdminOpenBrowser) { Start-Process $config.AdminWebUrl }
} catch {
    if ($null -ne $config) {
        Write-StartupFailureSummary $config $startedServices
        Stop-StartedServices $config $startedServices | Out-Null
    }
    Write-Error $_
    exit 1
}
