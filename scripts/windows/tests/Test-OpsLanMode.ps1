Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-lan-中文 空格-' + [Guid]::NewGuid().ToString('N'))
$fakeProcesses = @()

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
    } catch {
        return
    }
    throw "$Label should fail but did not."
}
function New-LanCandidate([string]$Address, [string]$Alias = 'Wi-Fi') {
    return [pscustomobject]@{ IPAddress=$Address; InterfaceIndex=17; InterfaceAlias=$Alias; InterfaceDescription=$Alias }
}

function New-NetworkProfile([string]$Category = 'Private') {
    return [pscustomobject]@{ InterfaceAlias='Wi-Fi'; NetworkName='Office Wi-Fi'; NetworkCategory=$Category; Detail='' }
}

try {
    foreach ($path in @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\status_ai_customer_service.ps1',
        'scripts\windows\start_lan_ai_customer_service.ps1',
        'scripts\windows\status_lan_ai_customer_service.ps1',
        'scripts\windows\config.local.ps1.example'
    )) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $repositoryRoot $path), [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "$path has a PowerShell syntax error: $($errors[0].Message)" }
    }
    foreach ($entry in @('启动局域网客服.bat', '检查局域网客服状态.bat')) {
        if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot "scripts\windows\$entry") -PathType Leaf)) { throw "缺少 LAN 入口：$entry" }
    }

    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $temporaryRepository = Join-Path $temporaryRoot '主仓库 空格'
    New-Item -ItemType Directory -Force -Path @(
        (Join-Path $temporaryRepository 'backend'),
        (Join-Path $temporaryRepository 'frontend'),
        (Join-Path $temporaryRepository 'platform_backend')
    ) | Out-Null
    $ragPython = Join-Path $temporaryRepository 'rag.exe'
    $platformPython = Join-Path $temporaryRepository 'platform.exe'
    New-Item -ItemType File -Path $ragPython, $platformPython | Out-Null
    $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $configPath = Join-Path $temporaryRoot 'config local 中文.ps1'
    @"
@{
    RepositoryRoot = '$($temporaryRepository.Replace("'", "''"))'
    RagPythonPath = '$($ragPython.Replace("'", "''"))'
    PlatformPythonPath = '$($platformPython.Replace("'", "''"))'
    PnpmCommand = '$($shellPath.Replace("'", "''"))'
    RagPort = 18000; CustomerWebPort = 15173; PlatformPort = 18011; BindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:15173/'
    RagHealthPath = '/api/health'; PlatformHealthPath = '/health'; OllamaModel = 'qwen3.5:9b'
    CorsAllowedOrigins = @('http://127.0.0.1:15173'); OpenBrowser = `$false
    RuntimeDirectory = '$((Join-Path $temporaryRoot 'runtime state').Replace("'", "''"))'
    TestDataPackagePath = ''; AutoImportTestData = `$false
}
"@ | Set-Content -LiteralPath $configPath -Encoding UTF8

    $config = Get-LocalConfig $configPath
    if ($config.BindAddress -ne '127.0.0.1' -or $config.LanMode -or $config.LanBindAddress -ne '0.0.0.0' -or $config.LanAdvertisedHost -ne '' -or $config.AllowPublicNetwork) {
        throw '本机模式兼容默认值不正确。'
    }

    foreach ($invalidIp in @('127.0.0.1', '169.254.1.10', '8.8.8.8', '0.0.0.0', '224.0.0.1', 'not-an-ip')) {
        if (Test-PrivateLanIpv4 $invalidIp) { throw "非法 LAN IP 被接受：$invalidIp" }
    }
    if (-not (Test-PrivateLanIpv4 '192.168.1.20')) { throw '私有 IPv4 被错误拒绝。' }
    if (Test-LanAdapterEligible ([pscustomobject]@{Status='Up';Name='DockerNAT';InterfaceDescription='Docker Virtual Ethernet'})) { throw '虚拟网卡未被排除。' }
    if (Test-LanAdapterEligible ([pscustomobject]@{Status='Disconnected';Name='Wi-Fi';InterfaceDescription='Wi-Fi'})) { throw '断开网卡未被排除。' }

    $candidate = New-LanCandidate '192.168.1.20'
    $privateProfile = New-NetworkProfile 'Private'
    $config.LanAdvertisedHost = ''
    $lanConfig = Resolve-LanRuntimeConfig $config @($candidate) $privateProfile
    if ($lanConfig.LanAdvertisedHost -ne '192.168.1.20' -or $lanConfig.BindAddress -ne '0.0.0.0' -or $lanConfig.CustomerWebUrl -ne 'http://192.168.1.20:15173/') {
        throw '唯一 IP 自动发现或 LAN 绑定错误。'
    }

    $config.LanAdvertisedHost = '192.168.1.20'
    $explicitConfig = Resolve-LanRuntimeConfig $config @($candidate, (New-LanCandidate '10.20.30.40' 'Ethernet')) $privateProfile
    if ($explicitConfig.LanAdvertisedHost -ne '192.168.1.20') { throw '明确 LAN IP 未被采用。' }
    $config.LanAdvertisedHost = ''
    Assert-Throws { Resolve-LanRuntimeConfig $config @($candidate, (New-LanCandidate '10.20.30.40' 'Ethernet')) $privateProfile | Out-Null } 'Multiple valid adapters must require configuration'

    $config.LanAdvertisedHost = '8.8.8.8'
    Assert-Throws { Resolve-LanRuntimeConfig $config @($candidate) $privateProfile | Out-Null } 'Public IP protection'
    $config.LanAdvertisedHost = '192.168.1.20'
    Assert-Throws { Resolve-LanRuntimeConfig $config @($candidate) (New-NetworkProfile 'Public') | Out-Null } 'Public network protection'
    $config.LanBindAddress = '8.8.8.8'
    Assert-Throws { Resolve-LanRuntimeConfig $config @($candidate) $privateProfile | Out-Null } 'Public bind protection'
    $config.LanBindAddress = '0.0.0.0'
    $lanConfig = Resolve-LanRuntimeConfig $config @($candidate) $privateProfile

    foreach ($port in @($lanConfig.RagPort, $lanConfig.PlatformPort, $lanConfig.CustomerWebPort)) {
        if ((Get-LanServiceListenerAddress $lanConfig $port) -ne "0.0.0.0:$port") { throw "LAN listener address is wrong for port $port" }
    }
    $expectedCors = 'http://192.168.1.20:15173,http://127.0.0.1:15173,http://localhost:15173'
    if ($lanConfig.LanCorsAllowedOrigins -ne $expectedCors -or $lanConfig.LanCorsAllowedOrigins -match '\*') { throw 'LAN CORS must use the three explicit origins.' }
    $platformEnvironment = Get-LanPlatformEnvironment $lanConfig
    $ragEnvironment = Get-LanRagEnvironment $lanConfig
    $frontendEnvironment = Get-LanFrontendEnvironment $lanConfig
    if ($platformEnvironment.CORS_ALLOWED_ORIGINS -ne $expectedCors -or $ragEnvironment.CORS_ALLOWED_ORIGINS -ne $expectedCors -or $frontendEnvironment.VITE_RAG_API_BASE_URL -ne 'http://192.168.1.20:18000' -or $frontendEnvironment.VITE_PLATFORM_API_BASE_URL -ne 'http://192.168.1.20:18011') {
        throw 'LAN A/C CORS or B API environment is wrong.'
    }

    $managedPort = 55173
    $managedCommand = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $managedPort + '); $listener.Start(); Start-Sleep -Seconds 30'
    $managedProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',$managedCommand) -WindowStyle Hidden -PassThru
    $fakeProcesses += $managedProcess
    Start-Sleep -Milliseconds 300
    Save-ServiceRecord $lanConfig 'customer-web' $managedProcess $shellPath $temporaryRoot 'managed LAN listener' 'TcpListener' $managedPort
    Assert-Throws { Assert-PortAvailable $lanConfig 'customer-web' $managedPort } 'Repeated LAN startup protection'
    Stop-ManagedService $lanConfig 'customer-web' | Out-Null
    if (Get-Process -Id $managedProcess.Id -ErrorAction SilentlyContinue) { throw 'Recorded process was not safely stopped.' }
    $fakeProcesses = @($fakeProcesses | Where-Object { $_.Id -ne $managedProcess.Id })

    $unknownPort = 55174
    $unknownCommand = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $unknownPort + '); $listener.Start(); Start-Sleep -Seconds 30'
    $unknownProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',$unknownCommand) -WindowStyle Hidden -PassThru
    $fakeProcesses += $unknownProcess
    Start-Sleep -Milliseconds 300
    Assert-Throws { Assert-PortAvailable $lanConfig 'rag' $unknownPort } 'Unknown port owner protection'
    if (-not (Get-Process -Id $unknownProcess.Id -ErrorAction SilentlyContinue)) { throw 'Unknown port owner was unexpectedly terminated.' }

    Write-Host 'OPS-T05-LAN 测试：PASS（本机兼容、IP 选择、Public 拦截、绑定/CORS/API、重复启动、安全停止、未知进程保护、语法与中文空格路径）。' -ForegroundColor Green
} finally {
    foreach ($process in $fakeProcesses) {
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd('\')) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
