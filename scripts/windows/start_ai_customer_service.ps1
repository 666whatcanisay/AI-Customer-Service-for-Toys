[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
$config = $null
$startedServices = @()
try {
    $config = Get-LocalConfig $ConfigPath
    Assert-RagVirtualEnvironment $config
    Assert-Dependencies $config
    foreach ($pair in @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort})) { Assert-PortAvailable $config $pair.Name $pair.Port }
    $env:CORS_ALLOWED_ORIGINS = (@($config.CorsAllowedOrigins) -join ',')
    $env:DATABASE_URL = $config.PlatformDatabaseUrl
    Invoke-PlatformMigration $config

    Start-ManagedService $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort | Out-Null
    $startedServices += 'platform'
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'

    Import-TestDataPackage $config | Out-Null
    $env:LLM_PROVIDER = 'ollama'
    $env:LLM_MODEL = $config.OllamaModel
    $env:LLM_BASE_URL = $config.OllamaBaseUrl
    $env:PLATFORM_API_BASE_URL = "http://127.0.0.1:$($config.PlatformPort)"
    Start-ManagedService $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort | Out-Null
    $startedServices += 'rag'
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    Wait-RagRuntimeReady $config 120 | Out-Null
    Sync-TestKnowledge $config | Out-Null
    Invoke-RagChatSmoke $config | Out-Null

    $vite = Join-Path $config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'
    Start-ManagedService $config 'customer-web' (Get-Command node.exe).Source @($vite,'--host',$config.BindAddress,'--port',$config.CustomerWebPort,'--strictPort') (Join-Path $config.RepositoryRoot 'frontend') 'vite.js' $config.CustomerWebPort | Out-Null
    $startedServices += 'customer-web'
    Wait-HttpOk $config.CustomerWebUrl 45 '客服页面'
    Write-Host "AI 客服已启动：$($config.CustomerWebUrl)" -ForegroundColor Green
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    if ([bool]$config.OpenBrowser) { Start-Process $config.CustomerWebUrl }
} catch {
    if ($null -ne $config) { Write-StartupFailureSummary $config $startedServices }
    Write-Error $_
    exit 1
}
