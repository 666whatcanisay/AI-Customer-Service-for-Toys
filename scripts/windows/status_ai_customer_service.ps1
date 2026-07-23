[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $config = Get-LocalConfig $ConfigPath
    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if (-not $ollama) { $ollama = Get-Command ollama -ErrorAction SilentlyContinue }
    $model = $false
    if ($ollama) {
        $models = & $ollama.Source list 2>$null
        $model = [bool]($models | Where-Object { $_ -match "^$([regex]::Escape($config.OllamaModel))\s" })
    }
    Write-Host "Ollama：$(if($ollama){'可用'}else{'不可用'})；模型 $($config.OllamaModel)：$(if($model){'存在'}else{'缺失'})"

    foreach ($item in @(
        @{Label='C';Name='platform';Port=$config.PlatformPort;Url=(Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath)},
        @{Label='A';Name='rag';Port=$config.RagPort;Url=(Get-ServiceUrl $config $config.RagPort $config.RagHealthPath)},
        @{Label='B';Name='customer-web';Port=$config.CustomerWebPort;Url=$config.CustomerWebUrl}
    )) {
        $serviceStatus = Get-ServiceStatus $config $item.Name $item.Port $item.Url
        Write-Host "$($item.Label)：$($serviceStatus.State)；PID $($serviceStatus.ProcessId)；端口 $($serviceStatus.Port)：$($serviceStatus.PortState)；health：$($serviceStatus.HealthState)"
    }

    $lan = if ($config.BindAddress -eq '127.0.0.1' -or $config.BindAddress -eq 'localhost') {'否'}else{'是'}
    $data = if ([string]::IsNullOrWhiteSpace([string]$config.TestDataPackagePath)) {'未配置'} else { "已配置（自动导入：$($config.AutoImportTestData)）" }
    Write-Host "客服地址：$($config.CustomerWebUrl)"
    Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"
    Write-Host "局域网模式：$lan"
    Write-Host "测试数据包：$data"
} catch {
    Write-Error $_
    exit 1
}
