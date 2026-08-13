[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$NoBrowser,
    [ValidateSet('Auto','Local','Lan')]
    [string]$Mode = 'Auto'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
$config = $null
$startedServices = @()
try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    $effectiveNetworkMode = Resolve-StandardRuntimeNetworkMode $config $Mode
    if ($effectiveNetworkMode -eq 'LAN') {
        Write-Host '通用启动入口已选择 LAN Runtime；A/C/Admin 保持本机回环，B 使用当前受控局域网地址。' -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot 'start_lan_ai_customer_service.ps1') -ConfigPath $resolvedConfigPath -NoBrowser:$NoBrowser
        if (-not $?) { throw 'LAN Runtime 启动入口执行失败。' }
        return
    }
    Assert-RagVirtualEnvironment $config
    Assert-Dependencies $config
    Assert-AdminWebDependencies $config | Out-Null
    Write-AiCsStartupPreflight $config $resolvedConfigPath
    $services = @(@{Name='platform';Port=$config.PlatformPort},@{Name='rag';Port=$config.RagPort},@{Name='customer-web';Port=$config.CustomerWebPort},@{Name='admin-web';Port=$config.AdminWebPort})
    Assert-ManagedRuntimeSourceConsistency $config $services
    $alreadyRunning = @($services | Where-Object { Test-ManagedServiceRunning $config $_.Name $_.Port })
    if ($alreadyRunning.Count -eq $services.Count) {
        try { Save-StandardRuntimeNetworkModePreference $config 'LOCAL' } catch { Write-Warning "无法保存 LOCAL Runtime 偏好：$($_.Exception.Message)" }
        Write-Host "AI 客服已运行：$($config.CustomerWebUrl)" -ForegroundColor Green
        Write-Host '使用检查AI客服状态.bat 查看状态，或使用停止AI客服.bat 安全停止。'
        return
    }
    if ($alreadyRunning.Count -gt 0) { throw "仅部分服务处于可信健康运行状态：$($alreadyRunning.Name -join ', ')。请先使用状态脚本核对，避免混合启动。" }
    foreach ($pair in $services) { Assert-PortAvailable $config $pair.Name $pair.Port }
    $platformEnvironment = Get-LocalPlatformEnvironment $config
    Invoke-WithProcessEnvironment $platformEnvironment { Assert-PlatformDatabaseReady $config } | Out-Null

    $startedServices += 'platform'
    Start-ManagedServiceWithEnvironment $config 'platform' $config.PlatformPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.PlatformPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'platform_backend') 'app.main:app' $config.PlatformPort $platformEnvironment | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) 60 '平台服务'
    Update-ManagedServiceListenerRecord $config 'platform' | Out-Null
    Write-Rc5RuntimeActivationManifest $config 'platform' $resolvedConfigPath | Out-Null

    $ragEnvironment = Get-LocalRagEnvironment $config
    $startedServices += 'rag'
    Start-ManagedServiceWithEnvironment $config 'rag' $config.RagPythonPath @('-m','uvicorn','app.main:app','--host',$config.BindAddress,'--port',$config.RagPort,'--no-access-log') (Join-Path $config.RepositoryRoot 'backend') 'app.main:app' $config.RagPort $ragEnvironment | Out-Null
    Wait-HttpOk (Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) 120 'RAG 服务'
    Update-ManagedServiceListenerRecord $config 'rag' | Out-Null
    Wait-RagRuntimeReady $config 120 | Out-Null
    $activeCollectionState = Get-RagActiveCollectionStartupState $config
    if (-not $activeCollectionState.Ready) { Write-Warning 'A active collection 未就绪；普通启动不会导入或同步测试知识。' }
    Write-Rc5RuntimeActivationManifest $config 'rag' $resolvedConfigPath | Out-Null

    $startedServices += 'customer-web'
    Start-CustomerWebService $config | Out-Null
    $startedServices += 'admin-web'
    Start-AdminWebService $config | Out-Null
    try { Save-StandardRuntimeNetworkModePreference $config 'LOCAL' } catch { Write-Warning "无法保存 LOCAL Runtime 偏好：$($_.Exception.Message)" }
    Write-Host "AI 客服已启动：$($config.CustomerWebUrl)" -ForegroundColor Green
    Write-Host "运营后台：$($config.AdminWebUrl)"
    Write-Host 'API 模式：PRODUCTION_SAME_ORIGIN_PROXY（静态构建；禁止 Vite dev server）'
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
