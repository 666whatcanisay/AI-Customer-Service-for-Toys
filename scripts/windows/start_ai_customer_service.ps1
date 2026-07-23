$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $config = Get-LocalConfig
    Assert-Dependencies $config
    foreach ($pair in @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort})) { Assert-PortAvailable $config $pair.Name $pair.Port }
    $env:CORS_ALLOWED_ORIGINS = (@($config.CorsAllowedOrigins) -join ',')
    $env:PLATFORM_API_BASE_URL = Get-ServiceUrl $config $config.PlatformPort ''
    Start-ManagedService $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'
    Import-TestDataPackage $config
    Start-ManagedService $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    $vite = Join-Path $config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'
    Start-ManagedService $config 'customer-web' (Get-Command node.exe).Source @($vite,'--host',$config.BindAddress,'--port',$config.CustomerWebPort,'--strictPort') (Join-Path $config.RepositoryRoot 'frontend') 'vite.js' $config.CustomerWebPort | Out-Null
    Wait-HttpOk $config.CustomerWebUrl 45 '客服页面'
    Write-Host "AI 客服已启动：$($config.CustomerWebUrl)" -ForegroundColor Green
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    if ([bool]$config.OpenBrowser) { Start-Process $config.CustomerWebUrl }
} catch { Write-Error $_; exit 1 }
