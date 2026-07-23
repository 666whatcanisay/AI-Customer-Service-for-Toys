[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

$config = $null
$startedServices = @()
try {
    $baseConfig = Get-LocalConfig $ConfigPath
    # This dedicated entry explicitly enables LAN mode without changing the local-mode entry or config file.
    $config = Resolve-LanRuntimeConfig $baseConfig
    $network = $config.LanNetworkProfile

    Write-Host "局域网 IP：$($config.LanAdvertisedHost)（$($network.InterfaceAlias)，$($network.NetworkCategory)）" -ForegroundColor Cyan
    Write-Host "服务绑定：A $(Get-LanServiceListenerAddress $config $config.RagPort)；C $(Get-LanServiceListenerAddress $config $config.PlatformPort)；B $(Get-LanServiceListenerAddress $config $config.CustomerWebPort)"
    Write-Host "局域网页面：$($config.CustomerWebUrl)"
    Write-Host (Get-LanFirewallStatusMessage $network) -ForegroundColor Yellow

    Assert-RagVirtualEnvironment $config
    Assert-Dependencies $config
    foreach ($pair in @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort})) {
        Assert-PortAvailable $config $pair.Name $pair.Port
    }

    $platformEnvironment = Get-LanPlatformEnvironment $config
    Invoke-WithProcessEnvironment $platformEnvironment { Invoke-PlatformMigration $config } | Out-Null

    Start-ManagedServiceWithEnvironment $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort $platformEnvironment | Out-Null
    $startedServices += 'platform'
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'

    Import-TestDataPackage $config | Out-Null

    $ragEnvironment = Get-LanRagEnvironment $config
    Start-ManagedServiceWithEnvironment $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort $ragEnvironment | Out-Null
    $startedServices += 'rag'
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    Wait-RagRuntimeReady $config 120 | Out-Null
    Sync-TestKnowledge $config | Out-Null
    Invoke-RagChatSmoke $config | Out-Null

    $vite = Join-Path $config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'
    $frontendEnvironment = Get-LanFrontendEnvironment $config
    Start-ManagedServiceWithEnvironment $config 'customer-web' (Get-Command node.exe).Source @($vite,'--host',$config.BindAddress,'--port',$config.CustomerWebPort,'--strictPort') (Join-Path $config.RepositoryRoot 'frontend') 'vite.js' $config.CustomerWebPort $frontendEnvironment | Out-Null
    $startedServices += 'customer-web'
    Wait-HttpOk (Get-ServiceUrl $config $config.CustomerWebPort '/') 45 '客服页面'

    Write-Host '局域网 AI 客服已启动。' -ForegroundColor Green
    Write-Host "本机页面：$($config.LocalCustomerWebUrl)"
    Write-Host "局域网页面：$($config.CustomerWebUrl)"
    Write-Host "前端 API：RAG=$($frontendEnvironment.VITE_RAG_API_BASE_URL)；平台=$($frontendEnvironment.VITE_PLATFORM_API_BASE_URL)"
    Write-Host "CORS_ALLOWED_ORIGINS=$($config.LanCorsAllowedOrigins)"
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    if ([bool]$config.OpenBrowser) { Start-Process $config.CustomerWebUrl }
} catch {
    Write-Error $_
    if ($null -ne $config) { Write-StartupFailureSummary $config $startedServices }
    exit 1
}
