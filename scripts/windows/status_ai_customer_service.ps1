[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $config = Get-LocalConfig $ConfigPath
    $env:DATABASE_URL = $config.PlatformDatabaseUrl
    $ollamaState = '不可用'
    try { Assert-OllamaReady $config | Out-Null; $ollamaState = '可用' } catch { $ollamaState = "不可用（$($_.Exception.Message)）" }
    Write-Host "Ollama：$ollamaState"
    Write-Host "Ollama 地址：$($config.OllamaBaseUrl)；模型：$($config.OllamaModel)"

    foreach ($item in @(
        @{Label='C';Name='platform';Port=$config.PlatformPort;Url=(Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath)},
        @{Label='A';Name='rag';Port=$config.RagPort;Url=(Get-ServiceUrl $config $config.RagPort $config.RagHealthPath)},
        @{Label='B';Name='customer-web';Port=$config.CustomerWebPort;Url=$config.CustomerWebUrl},
        @{Label='Admin';Name='admin-web';Port=$config.AdminWebPort;Url=(Get-ManagedServiceHealthUrl $config 'admin-web')}
    )) {
        $serviceStatus = Get-ServiceStatus $config $item.Name $item.Port $item.Url
        Write-Host "$($item.Label)：$($serviceStatus.State)；受管 PID $($serviceStatus.ManagedProcessId)；监听 PID $($serviceStatus.ListenerProcessId)；端口 $($serviceStatus.Port)：$($serviceStatus.PortState)；health：$($serviceStatus.HealthState)"
        Write-Host "  运行版本：$($serviceStatus.RuntimeIdentityState)；SHA $($serviceStatus.RuntimeGitShortSha)；源码 $($serviceStatus.RuntimeSourceState)；runtimeMode=$($serviceStatus.RuntimeMode)；networkMode=$($serviceStatus.NetworkMode)；$($serviceStatus.RuntimeIdentityDetail)"
    }
    $adminCheck = Test-RecordedProcess $config 'admin-web'
    $adminRecord = if ($adminCheck) { $adminCheck.Record } else { $null }
    $adminListenerPid = if ($adminRecord -and ($adminRecord.PSObject.Properties.Name -contains 'listener_pid')) { [string]$adminRecord.listener_pid } else { '未记录' }
    $adminLan = if ([bool]$config.AdminEnableLanMode) { '是（本轮未修改防火墙）' } else { '否（仅服务器本机）' }
    Write-Host "运营后台地址：$($config.AdminWebUrl)；监听地址：$($config.AdminWebBindAddress):$($config.AdminWebPort)；监听 PID：$adminListenerPid"
    Write-Host "运营后台 LAN 模式：$adminLan；日志：$(Join-Path (Get-ServiceLogDirectory $config) 'admin-web.out.log')；$(Join-Path (Get-ServiceLogDirectory $config) 'admin-web.err.log')"

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

    $lan = if ($config.BindAddress -eq '127.0.0.1' -or $config.BindAddress -eq 'localhost') {'否'}else{'是'}
    $data = if ([string]::IsNullOrWhiteSpace([string]$config.TestDataPackagePath)) {'未配置'} else { "已配置（自动导入：$($config.AutoImportTestData)）" }
    Write-Host "客服地址：$($config.CustomerWebUrl)"
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    Write-Host "局域网模式：$lan"
    Write-Host "测试 ZIP：$data；自动同步：$($config.AutoSyncTestKnowledge)"
} catch {
    Write-Error $_
    exit 1
}
