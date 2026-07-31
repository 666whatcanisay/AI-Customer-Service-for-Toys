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
        # Prefer the validated managed runtime record. Dynamic Windows adapter
        # discovery is retained only as a fallback because some hosts block the
        # networking cmdlets for minutes while the services remain healthy.
        $config = Resolve-LanStatusRuntimeConfig $baseConfig
    } catch {
        $lanResolutionError = $_.Exception.Message
        $config = $baseConfig
    }

    $env:DATABASE_URL = $config.PlatformDatabaseUrl
    $ollamaState = '不可用'
    try { Assert-OllamaReady $config | Out-Null; $ollamaState = '可用' } catch { $ollamaState = "不可用（$($_.Exception.Message)）" }
    Write-Host "Ollama：$ollamaState"
    Write-Host "Ollama 地址：$($config.OllamaBaseUrl)；模型：$($config.OllamaModel)"

    $serviceDefinitions = @(
        @{Label='C';Name='platform';Port=$config.PlatformPort;Url=(Get-ManagedServiceHealthUrl $config 'platform')},
        @{Label='A';Name='rag';Port=$config.RagPort;Url=(Get-ManagedServiceHealthUrl $config 'rag')},
        @{Label='B';Name='customer-web';Port=$config.CustomerWebPort;Url=(Get-ManagedServiceHealthUrl $config 'customer-web')}
        @{Label='Admin';Name='admin-web';Port=$config.AdminWebPort;Url=(Get-ManagedServiceHealthUrl $config 'admin-web')}
    )
    $healthResults = Get-ParallelHttpHealth $serviceDefinitions 3000
    foreach ($item in @($serviceDefinitions | Where-Object { $_.Name -ne 'admin-web' })) {
        $serviceStatus = Get-ServiceStatus $config $item.Name $item.Port $item.Url $healthResults[$item.Name]
        $listener = if ($lanResolutionError) { '无法确定' } else { Get-LanServiceListenerAddress $config $item.Port }
        Write-Host "$($item.Label)：$($serviceStatus.State)；受管 PID $($serviceStatus.ManagedProcessId)；监听 PID $($serviceStatus.ListenerProcessId)；监听地址：$listener；端口 $($serviceStatus.Port)：$($serviceStatus.PortState)；health：$($serviceStatus.HealthState)"
        Write-Host "  运行版本：$($serviceStatus.RuntimeIdentityState)；SHA $($serviceStatus.RuntimeGitShortSha)；源码 $($serviceStatus.RuntimeSourceState)；runtimeMode=$($serviceStatus.RuntimeMode)；networkMode=$($serviceStatus.NetworkMode)；$($serviceStatus.RuntimeIdentityDetail)"
    }
    $adminStatus = Get-ServiceStatus $config 'admin-web' $config.AdminWebPort (Get-ManagedServiceHealthUrl $config 'admin-web') $healthResults['admin-web']
    $adminCheck = Test-RecordedProcess $config 'admin-web'
    $adminRecord = if ($adminCheck) { $adminCheck.Record } else { $null }
    $adminListenerPid = if ($adminRecord -and ($adminRecord.PSObject.Properties.Name -contains 'listener_pid')) { [string]$adminRecord.listener_pid } else { '未记录' }
    $adminLan = if ([bool]$config.AdminEnableLanMode) { '是（本轮未修改防火墙）' } else { '否（仅服务器本机）' }
    Write-Host "Admin：$($adminStatus.State)；受管 PID $($adminStatus.ManagedProcessId)；监听 PID $($adminStatus.ListenerProcessId)；监听地址：$($config.AdminWebBindAddress):$($config.AdminWebPort)；端口 $($adminStatus.Port)：$($adminStatus.PortState)；health：$($adminStatus.HealthState)"
    Write-Host "  运行版本：$($adminStatus.RuntimeIdentityState)；SHA $($adminStatus.RuntimeGitShortSha)；源码 $($adminStatus.RuntimeSourceState)；runtimeMode=$($adminStatus.RuntimeMode)；networkMode=$($adminStatus.NetworkMode)；$($adminStatus.RuntimeIdentityDetail)"
    Write-Host "运营后台地址：$($config.AdminWebUrl)；监听 PID：$adminListenerPid；LAN 模式：$adminLan；日志：$(Join-Path (Get-ServiceLogDirectory $config) 'admin-web.out.log')；$(Join-Path (Get-ServiceLogDirectory $config) 'admin-web.err.log')"

    Write-Host "C 数据库迁移：$(Get-PlatformMigrationStatus $config)"
    try {
        $package = @(Get-TestDataPackage $config)
        $packageState = if ($package.Count -eq 1) { "存在（$($package[0].import_status)）" } else { '不存在' }
    } catch { $packageState = "无法检查（$($_.Exception.Message)）" }
    Write-Host "测试包 $($config.TestKnowledgePackageId)：$packageState"

    $syncHistory = Get-TestKnowledgeSyncHistory $config
    $syncState = switch ($syncHistory.State) {
        'HISTORICAL_SYNC' { "历史同步记录：$($syncHistory.SyncedItems)/$($syncHistory.CollectionCount) 条（$($syncHistory.VerifiedUtc) UTC；不是当前运行时证明）" }
        'OTHER_PACKAGE_HISTORY' { "历史记录对应其他测试包：$($syncHistory.PackageId)" }
        'INVALID_HISTORY' { '历史同步记录无法解析' }
        default { '尚无成功同步历史记录' }
    }
    Write-Host "A 同步知识历史：$syncState"

    $knowledgeRuntime = Get-RagKnowledgeRuntimeStatistics $config
    $knowledgeConsistency = Get-TestKnowledgeRuntimeConsistency $syncHistory $knowledgeRuntime $config.RagActiveCollectionName
    if ($knowledgeRuntime.State -eq 'AVAILABLE') {
        Write-Host "A active collection：状态=$knowledgeConsistency；collection=$($knowledgeRuntime.ActiveCollectionName)；chunks=$($knowledgeRuntime.ActiveCollectionChunkCount)"
        Write-Host "A available collections：$(Format-RagAvailableCollections $knowledgeRuntime)；total_chunks=$($knowledgeRuntime.ChunkCount)；documents=$($knowledgeRuntime.DocumentCount)；database=$($knowledgeRuntime.VectorDatabase)"
        if ($knowledgeConsistency -eq 'MISMATCH') {
            Write-Host "警告：A active collection chunks=$($knowledgeRuntime.ActiveCollectionChunkCount) 与历史同步 collectionCount=$($syncHistory.CollectionCount) 不一致。不能将历史记录视为当前服务状态。" -ForegroundColor Red
        } elseif ($knowledgeConsistency -eq 'ACTIVE_COLLECTION_MISMATCH') {
            Write-Host "警告：A active collection=$($knowledgeRuntime.ActiveCollectionName) 与配置=$($config.RagActiveCollectionName) 不一致。" -ForegroundColor Red
        }
    } else {
        Write-Host "警告：无法读取 A 当前运行时知识统计：$($knowledgeRuntime.Error)" -ForegroundColor Red
    }

    try {
        $ragStatus = Get-Json (Get-ServiceUrl $config $config.RagPort '/api/status') 'A 状态'
        $modelState = "model_configured=$($ragStatus.model_configured)；ready=$($ragStatus.ready)；initialization_error=$($ragStatus.initialization_error)"
    } catch { $modelState = "无法读取（$($_.Exception.Message)）" }
    Write-Host "A 模型状态：$modelState"

    if ($lanResolutionError) {
        Write-Host "局域网页面：未确定（$lanResolutionError）" -ForegroundColor Yellow
        Write-Host '当前网络配置类型：无法确定'
        Write-Host '防火墙可能阻断提示：局域网 IP 未通过校验；脚本未修改防火墙或网络设置。' -ForegroundColor Yellow
    } else {
        $network = $config.LanNetworkProfile
        Write-Host "局域网页面：$($config.CustomerWebUrl)"
        Write-Host "当前网络配置类型：$($network.NetworkCategory)；适配器：$($network.InterfaceAlias)；网络：$($network.NetworkName)；来源：$($config.LanStatusResolutionSource)"
        Write-Host "选定网卡：$($config.LanSelection.InterfaceAlias)；IPv4：$($config.LanSelection.IPAddress)；子网掩码：$($config.LanSelection.SubnetMask)；默认网关：$($config.LanSelection.DefaultGateway)"
        if ([string]$network.NetworkCategory -eq 'Public' -and -not [bool]$config.AllowPublicNetwork) {
            Write-Host 'Public 网络：启动局域网客服会被阻止。请在 Windows 设置中将当前网络改为 Private 后重试。' -ForegroundColor Yellow
        }
        Write-Host (Get-LanFirewallStatusMessage $network) -ForegroundColor Yellow
        if ([string]$config.LanStatusResolutionSource -eq 'MANAGED_RECORD') {
            Write-Host '提示：为避免状态命令被Windows网卡发现阻塞，本次未重新扫描网卡/网关；如需实时网络详情请运行 diagnose_lan_ai_customer_service.ps1。' -ForegroundColor Yellow
        }
        Write-Host '前端 API：RAG=/rag-api；平台=/platform-api；模式=SAME_ORIGIN_PROXY'
        Write-Host '外部入口：仅 TCP 5173；A/C 仅监听 127.0.0.1。'
    }
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
} catch {
    Write-Error $_
    exit 1
}
