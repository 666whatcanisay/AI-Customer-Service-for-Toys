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
    $baseConfig = Get-LocalConfig $ConfigPath
    # This dedicated entry explicitly enables LAN mode without changing the local-mode entry or config file.
    $config = Resolve-LanRuntimeConfig $baseConfig
    $network = $config.LanNetworkProfile

    $selection = $config.LanSelection
    $vpnRisk = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { ("$($_.Name) $($_.InterfaceDescription)") -match '(?i)(vpn|tun|tap|wireguard|tailscale|zerotier)' })
    Write-Host "选择网卡：$($selection.InterfaceAlias)（$($selection.InterfaceDescription)）" -ForegroundColor Cyan
    Write-Host "IPv4：$($selection.IPAddress)；子网掩码：$($selection.SubnetMask)；默认网关：$($selection.DefaultGateway)；网段：$($config.LanSubnet)"
    Write-Host "网络配置类型：$($network.NetworkCategory)；检测到 VPN：$(if ($vpnRisk.Count -gt 0) { '是（' + (($vpnRisk | ForEach-Object { $_.Name }) -join '、') + '）' } else { '否' })"
    Write-Host "服务绑定：A $(Get-LanServiceListenerAddress $config $config.RagPort)；C $(Get-LanServiceListenerAddress $config $config.PlatformPort)；B $(Get-LanServiceListenerAddress $config $config.CustomerWebPort)"
    Write-Host "局域网页面：$($config.CustomerWebUrl)"
    Write-Host (Get-LanFirewallStatusMessage $network) -ForegroundColor Yellow

    Assert-RagVirtualEnvironment $config
    Assert-Dependencies $config
    Assert-AdminWebDependencies $config | Out-Null
    $services = @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort},@{Name='admin-web';Port=$config.AdminWebPort})
    Assert-ManagedRuntimeSourceConsistency $config $services
    $alreadyRunning = @($services | Where-Object { Test-ManagedServiceRunning $config $_.Name $_.Port })
    if ($alreadyRunning.Count -eq $services.Count) {
        Write-Host "局域网 AI 客服已运行：$($config.CustomerWebUrl)" -ForegroundColor Green
        Write-Host '使用检查局域网客服状态.bat 查看状态，或使用停止AI客服.bat 安全停止。'
        return
    }
    if ($alreadyRunning.Count -gt 0) { throw "仅部分服务处于可信健康运行状态：$($alreadyRunning.Name -join ', ')。请先使用状态脚本核对，避免混合启动。" }
    foreach ($pair in $services) { Assert-PortAvailable $config $pair.Name $pair.Port }

    $platformEnvironment = Get-LanPlatformEnvironment $config
    Invoke-WithProcessEnvironment $platformEnvironment { Invoke-PlatformMigration $config } | Out-Null

    Start-ManagedServiceWithEnvironment $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.PlatformBindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort $platformEnvironment | Out-Null
    $startedServices += 'platform'
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'
    Update-ManagedServiceListenerRecord $config 'platform' | Out-Null

    Import-TestDataPackage $config | Out-Null

    $ragEnvironment = Get-LanRagEnvironment $config
    Start-ManagedServiceWithEnvironment $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.RagBindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort $ragEnvironment | Out-Null
    $startedServices += 'rag'
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    Update-ManagedServiceListenerRecord $config 'rag' | Out-Null
    Wait-RagRuntimeReady $config 120 | Out-Null
    Sync-TestKnowledge $config | Out-Null
    Invoke-RagChatSmoke $config | Out-Null

    $vite = Join-Path $config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'
    $frontendEnvironment = Get-LanFrontendEnvironment $config
    Start-ManagedServiceWithEnvironment $config 'customer-web' (Get-Command node.exe).Source @($vite,'--host',$config.CustomerWebBindAddress,'--port',$config.CustomerWebPort,'--strictPort') (Join-Path $config.RepositoryRoot 'frontend') 'vite.js' $config.CustomerWebPort $frontendEnvironment | Out-Null
    $startedServices += 'customer-web'
    Wait-HttpOk $config.CustomerWebUrl 45 '客服页面'
    Update-ManagedServiceListenerRecord $config 'customer-web' | Out-Null
    Start-AdminWebService $config | Out-Null
    $startedServices += 'admin-web'

    Write-Host '局域网 AI 客服已启动。' -ForegroundColor Green
    Write-Host "局域网页面：$($config.CustomerWebUrl)"
    Write-Host "运营后台（默认仅服务器本机）：$($config.AdminWebUrl)"
    Write-Host "前端 API：RAG=$($frontendEnvironment.VITE_RAG_API_BASE_URL)；平台=$($frontendEnvironment.VITE_PLATFORM_API_BASE_URL)"
    Write-Host 'API 模式：SAME_ORIGIN_PROXY（浏览器仅连接 5173；A/C 只监听 127.0.0.1）'
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    if (-not $NoBrowser -and [bool]$config.OpenBrowser) { Start-Process $config.CustomerWebUrl }
    if (-not $NoBrowser -and [bool]$config.AdminOpenBrowser) { Start-Process $config.AdminWebUrl }
} catch {
    Write-Error $_
    if ($null -ne $config) { Write-StartupFailureSummary $config $startedServices }
    exit 1
}
