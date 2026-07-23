$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $config = Get-LocalConfig
    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue; if (-not $ollama) { $ollama = Get-Command ollama -ErrorAction SilentlyContinue }
    $model = $false; if ($ollama) { $models = & $ollama.Source list 2>$null; $model = [bool]($models | Where-Object { $_ -match "^$([regex]::Escape($config.OllamaModel))\s" }) }
    Write-Host "Ollama：$(if($ollama){'可用'}else{'不可用'})；模型 $($config.OllamaModel)：$(if($model){'存在'}else{'缺失'})"
    foreach ($item in @(@{Name='platform';Port=$config.PlatformPort;Url=(Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath)},@{Name='rag';Port=$config.RagPort;Url=(Get-ServiceUrl $config $config.RagPort $config.RagHealthPath)},@{Name='customer-web';Port=$config.CustomerWebPort;Url=$config.CustomerWebUrl})) { $record = Test-RecordedProcess $config $item.Name; $pid = if($record -and $record.Process){$record.Process.Id}else{'-'}; $state = if($record -and $record.Valid){'本工具运行中'}elseif($record){$record.Reason}else{'无记录'}; $http = if(Test-HttpOk $item.Url){'HTTP 正常'}else{'HTTP 不可用'}; Write-Host "$($item.Name)：$state；PID $pid；端口 $($item.Port)；$http" }
    $lan = if ($config.BindAddress -eq '127.0.0.1' -or $config.BindAddress -eq 'localhost') {'否'}else{'是'}
    $data = if ([string]::IsNullOrWhiteSpace([string]$config.TestDataPackagePath)) {'未配置'} else { "已配置（自动导入：$($config.AutoImportTestData)）" }
    Write-Host "客服地址：$($config.CustomerWebUrl)"; Write-Host "日志目录：$(Get-ServiceLogDirectory $config)"; Write-Host "局域网模式：$lan"; Write-Host "测试数据包：$data"
} catch { Write-Error $_; exit 1 }
