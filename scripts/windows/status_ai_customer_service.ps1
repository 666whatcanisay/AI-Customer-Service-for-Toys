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
        @{Label='B';Name='customer-web';Port=$config.CustomerWebPort;Url=$config.CustomerWebUrl}
    )) {
        $serviceStatus = Get-ServiceStatus $config $item.Name $item.Port $item.Url
        Write-Host "$($item.Label)：$($serviceStatus.State)；PID $($serviceStatus.ProcessId)；端口 $($serviceStatus.Port)：$($serviceStatus.PortState)；health：$($serviceStatus.HealthState)"
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
