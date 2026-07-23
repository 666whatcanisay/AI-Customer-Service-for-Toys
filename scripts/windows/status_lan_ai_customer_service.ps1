[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $baseConfig = Get-LocalConfig $ConfigPath
    $config = $null
    $lanResolutionError = $null
    try {
        # Status never silently starts services, so it reports a Public profile instead of applying the start guard.
        $config = Resolve-LanRuntimeConfig $baseConfig $null $null -SkipPublicNetworkGuard
    } catch {
        $lanResolutionError = $_.Exception.Message
        $config = $baseConfig
    }

    $env:DATABASE_URL = $config.PlatformDatabaseUrl
    $ollamaState = '不可用'
    try { Assert-OllamaReady $config | Out-Null; $ollamaState = '可用' } catch { $ollamaState = "不可用（$($_.Exception.Message)）" }
    Write-Host "Ollama：$ollamaState"
    Write-Host "Ollama 地址：$($config.OllamaBaseUrl)；模型：$($config.OllamaModel)"

    foreach ($item in @(
        @{Label='C';Name='platform';Port=$config.PlatformPort;Url=(Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath)},
        @{Label='A';Name='rag';Port=$config.RagPort;Url=(Get-ServiceUrl $config $config.RagPort $config.RagHealthPath)},
        @{Label='B';Name='customer-web';Port=$config.CustomerWebPort;Url=(Get-ServiceUrl $config $config.CustomerWebPort '/')}
    )) {
        $serviceStatus = Get-ServiceStatus $config $item.Name $item.Port $item.Url
        $listener = if ($lanResolutionError) { '无法确定' } else { Get-LanServiceListenerAddress $config $item.Port }
        Write-Host "$($item.Label)：$($serviceStatus.State)；PID $($serviceStatus.ProcessId)；监听地址：$listener；端口 $($serviceStatus.Port)：$($serviceStatus.PortState)；health：$($serviceStatus.HealthState)"
    }

    Write-Host "C 数据库迁移：$(Get-PlatformMigrationStatus $config)"
    try {
        $package = @(Get-TestDataPackage $config)
        $packageState = if ($package.Count -eq 1) { "存在（$($package[0].import_status)）" } else { '不存在' }
    } catch { $packageState = "无法检查（$($_.Exception.Message)）" }
    Write-Host "测试包 $($config.TestKnowledgePackageId)：$packageState"

    $syncPath = Get-TestKnowledgeSyncRecordPath $config
    if (Test-Path -LiteralPath $syncPath) {
        try {
            $sync = Get-Content -LiteralPath $syncPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$sync.packageId -eq [string]$config.TestKnowledgePackageId) {
                $syncState = "最后验证 $($sync.syncedItems)/$($sync.collectionCount) 条（$($sync.verifiedUtc) UTC）"
            } else { $syncState = '记录对应其他测试包' }
        } catch { $syncState = '运行记录无法解析' }
    } else { $syncState = '尚无成功同步记录' }
    Write-Host "A 同步知识数量：$syncState"

    try {
        $ragStatus = Get-Json (Get-ServiceUrl $config $config.RagPort '/api/status') 'A 状态'
        $modelState = "model_configured=$($ragStatus.model_configured)；ready=$($ragStatus.ready)；initialization_error=$($ragStatus.initialization_error)"
    } catch { $modelState = "无法读取（$($_.Exception.Message)）" }
    Write-Host "A 模型状态：$modelState"

    Write-Host "本机页面：http://127.0.0.1:$($config.CustomerWebPort)/"
    if ($lanResolutionError) {
        Write-Host "局域网页面：未确定（$lanResolutionError）" -ForegroundColor Yellow
        Write-Host '当前网络配置类型：无法确定'
        Write-Host '防火墙可能阻断提示：局域网 IP 未通过校验；脚本未修改防火墙或网络设置。' -ForegroundColor Yellow
    } else {
        $network = $config.LanNetworkProfile
        Write-Host "局域网页面：$($config.CustomerWebUrl)"
        Write-Host "当前网络配置类型：$($network.NetworkCategory)；适配器：$($network.InterfaceAlias)；网络：$($network.NetworkName)"
        if ([string]$network.NetworkCategory -eq 'Public' -and -not [bool]$config.AllowPublicNetwork) {
            Write-Host 'Public 网络：启动局域网客服会被阻止。请在 Windows 设置中将当前网络改为 Private 后重试。' -ForegroundColor Yellow
        }
        Write-Host (Get-LanFirewallStatusMessage $network) -ForegroundColor Yellow
        Write-Host "前端 API：RAG=http://$($config.LanAdvertisedHost):$($config.RagPort)；平台=http://$($config.LanAdvertisedHost):$($config.PlatformPort)"
        Write-Host "CORS_ALLOWED_ORIGINS=$($config.LanCorsAllowedOrigins)"
    }
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
} catch {
    Write-Error $_
    exit 1
}
