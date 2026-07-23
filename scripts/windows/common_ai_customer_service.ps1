Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LocalConfig([string]$ConfigPath) {
    $configPath = if ([string]::IsNullOrWhiteSpace($ConfigPath)) { Join-Path $PSScriptRoot 'config.local.ps1' } else { $ConfigPath }
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "缺少本地配置：$configPath。请将 config.local.ps1.example 复制为 config.local.ps1 后填写。"
    }
    $config = & $configPath
    if ($null -eq $config -or -not ($config -is [hashtable])) { throw 'config.local.ps1 必须返回一个 hashtable（请以示例文件为准）。' }
    $optionalDefaults = [ordered]@{
        OllamaBaseUrl = 'http://127.0.0.1:11434'
        PlatformDatabaseUrl = 'sqlite:///./platform.db'
        TestKnowledgePackageId = 'PDD-SM-2026-001-TEST'
        AutoSyncTestKnowledge = $true
        LanMode = $false
        LanBindAddress = '0.0.0.0'
        LanAdvertisedHost = ''
        AllowPublicNetwork = $false
    }
    foreach ($entry in $optionalDefaults.GetEnumerator()) {
        if (-not $config.ContainsKey($entry.Key) -or $null -eq $config[$entry.Key] -or [string]::IsNullOrWhiteSpace([string]$config[$entry.Key])) {
            $config[$entry.Key] = $entry.Value
        }
    }
    foreach ($key in @('RepositoryRoot','RagPythonPath','PlatformPythonPath','PnpmCommand','RagPort','CustomerWebPort','PlatformPort','BindAddress','CustomerWebUrl','RagHealthPath','PlatformHealthPath','OllamaModel','CorsAllowedOrigins','OpenBrowser','RuntimeDirectory','AutoImportTestData')) {
        if (-not $config.ContainsKey($key) -or $null -eq $config[$key] -or [string]::IsNullOrWhiteSpace([string]$config[$key])) { throw "配置项 $key 缺失或为空。" }
    }
    try { $root = (Resolve-Path -LiteralPath $config.RepositoryRoot -ErrorAction Stop).Path } catch { throw "RepositoryRoot 不存在：$($config.RepositoryRoot)" }
    foreach ($directory in @('backend','frontend','platform_backend')) { if (-not (Test-Path -LiteralPath (Join-Path $root $directory))) { throw "RepositoryRoot 不含 $directory：$root" } }
    $config.RepositoryRoot = $root
    if ([string]::IsNullOrWhiteSpace([string]$config.RuntimeDirectory)) { $config.RuntimeDirectory = Join-Path $root '.runtime' }
    foreach ($name in @('RagPort','CustomerWebPort','PlatformPort')) {
        $port = 0
        if (-not [int]::TryParse([string]$config[$name], [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw "$name 必须为 1-65535 的端口。" }
        $config[$name] = $port
    }
    if ((@($config.RagPort,$config.CustomerWebPort,$config.PlatformPort) | Select-Object -Unique).Count -ne 3) { throw '三个服务端口必须不同。' }
    foreach ($pathKey in @('RagPythonPath','PlatformPythonPath')) { if (-not (Test-Path -LiteralPath $config[$pathKey])) { throw "$pathKey 不存在：$($config[$pathKey])" } }
    if (-not (Get-Command $config.PnpmCommand -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $config.PnpmCommand)) { throw "PnpmCommand 不可用：$($config.PnpmCommand)" }
    if (@($config.CorsAllowedOrigins).Count -eq 0) { throw 'CorsAllowedOrigins 至少要有一个来源。' }
    try {
        $ollamaUri = [uri]$config.OllamaBaseUrl
        if (-not $ollamaUri.IsAbsoluteUri -or $ollamaUri.Scheme -notin @('http', 'https') -or [string]::IsNullOrWhiteSpace($ollamaUri.Host)) {
            throw 'invalid'
        }
        $config.OllamaBaseUrl = $ollamaUri.AbsoluteUri.TrimEnd('/')
    } catch {
        throw "OllamaBaseUrl 必须是有效的 http(s) 地址：$($config.OllamaBaseUrl)"
    }
    foreach ($key in @('PlatformDatabaseUrl', 'TestKnowledgePackageId')) {
        if ([string]::IsNullOrWhiteSpace([string]$config[$key])) { throw "配置项 $key 缺失或为空。" }
    }
    foreach ($key in @('OpenBrowser', 'AutoImportTestData', 'AutoSyncTestKnowledge', 'LanMode', 'AllowPublicNetwork')) {
        if ($config[$key] -isnot [bool]) {
            $parsed = $false
            if (-not [bool]::TryParse([string]$config[$key], [ref]$parsed)) { throw "配置项 $key 必须为 true 或 false。" }
            $config[$key] = $parsed
        }
    }
    return $config
}

function Get-ServiceRecordPath($Config, [string]$Name) { Join-Path $Config.RuntimeDirectory "$Name.json" }
function Get-ServiceLogDirectory($Config) { Join-Path $Config.RuntimeDirectory 'logs' }
function Get-ServiceUrl($Config, [int]$Port, [string]$Path = '/') {
    $serviceHost = [string]$Config.BindAddress
    if ($serviceHost -in @('0.0.0.0', '::')) { $serviceHost = '127.0.0.1' }
    "http://${serviceHost}:$Port$Path"
}

function Test-PrivateLanIpv4([string]$Address) {
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes[0] -eq 10) { return $true }
    if ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) { return $true }
    return $bytes[0] -eq 192 -and $bytes[1] -eq 168
}

function Test-LanAdapterEligible($Adapter) {
    if ([string]$Adapter.Status -ne 'Up') { return $false }
    $description = "{0} {1}" -f [string]$Adapter.Name, [string]$Adapter.InterfaceDescription
    return $description -notmatch '(?i)(virtual|vmware|hyper-v|vEthernet|wsl|docker|loopback|tunnel|tap|vpn)'
}

function Get-LanIpv4Candidates {
    $candidates = @()
    try {
        $adapters = @(Get-NetAdapter -ErrorAction Stop)
    } catch {
        throw "无法读取 Windows 网络适配器：$($_.Exception.Message)"
    }
    foreach ($adapter in $adapters) {
        if (-not (Test-LanAdapterEligible $adapter)) { continue }
        $interfaceIndex = [int]$adapter.ifIndex
        $addresses = @(Get-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
        foreach ($address in $addresses) {
            $ip = [string]$address.IPAddress
            if (-not (Test-PrivateLanIpv4 $ip)) { continue }
            $candidates += [pscustomobject]@{
                IPAddress = $ip
                InterfaceIndex = $interfaceIndex
                InterfaceAlias = [string]$adapter.Name
                InterfaceDescription = [string]$adapter.InterfaceDescription
            }
        }
    }
    return @($candidates | Sort-Object IPAddress -Unique)
}

function Get-LanNetworkProfile($Candidate) {
    try {
        $profiles = @(Get-NetConnectionProfile -InterfaceIndex ([int]$Candidate.InterfaceIndex) -ErrorAction Stop)
    } catch {
        return [pscustomobject]@{ InterfaceAlias=[string]$Candidate.InterfaceAlias; NetworkName=''; NetworkCategory='Unknown'; Detail=$_.Exception.Message }
    }
    $profile = $profiles | Select-Object -First 1
    if ($null -eq $profile) {
        return [pscustomobject]@{ InterfaceAlias=[string]$Candidate.InterfaceAlias; NetworkName=''; NetworkCategory='Unknown'; Detail='Windows 未返回网络配置文件' }
    }
    return [pscustomobject]@{
        InterfaceAlias = [string]$Candidate.InterfaceAlias
        NetworkName = [string]$profile.Name
        NetworkCategory = [string]$profile.NetworkCategory
        Detail = ''
    }
}

function Assert-LanNetworkSafety($Config, $NetworkProfile) {
    if ([string]$NetworkProfile.NetworkCategory -eq 'Public') {
        if (-not [bool]$Config.AllowPublicNetwork) {
            throw "当前网络 [$($NetworkProfile.NetworkName)]（$($NetworkProfile.InterfaceAlias)）配置为 Public。为避免在公共网络暴露测试服务，局域网启动已阻止；请在 Windows 设置中将该网络改为 Private 后重试。"
        }
        Write-Warning "当前网络 [$($NetworkProfile.NetworkName)] 配置为 Public；因 AllowPublicNetwork=true 正在继续。请确认这是受控网络，脚本不会修改防火墙。"
    }
}

function Get-LanCorsAllowedOrigins($Config) {
    $lanOrigin = "http://$($Config.LanAdvertisedHost):$($Config.CustomerWebPort)"
    $origins = @($lanOrigin, "http://127.0.0.1:$($Config.CustomerWebPort)", "http://localhost:$($Config.CustomerWebPort)") | Select-Object -Unique
    if (@($origins | Where-Object { $_ -eq '*' -or $_ -match '\*' }).Count -gt 0) { throw '局域网 CORS 只允许显式 Origin，禁止通配符。' }
    return ($origins -join ',')
}

function Resolve-LanRuntimeConfig($Config, [object[]]$Candidates, $NetworkProfile, [switch]$SkipPublicNetworkGuard) {
    if ([string]$Config.LanBindAddress -ne '0.0.0.0') {
        throw "LanBindAddress 必须为 0.0.0.0；拒绝绑定到指定地址或公网 IP：$($Config.LanBindAddress)"
    }
    if ($null -eq $Candidates) { $Candidates = @(Get-LanIpv4Candidates) }
    $configuredHost = [string]$Config.LanAdvertisedHost
    $selected = $null
    if (-not [string]::IsNullOrWhiteSpace($configuredHost)) {
        if (-not (Test-PrivateLanIpv4 $configuredHost)) {
            throw "LanAdvertisedHost 必须是主电脑有效的私有 IPv4；拒绝地址：$configuredHost"
        }
        $selected = @($Candidates | Where-Object { [string]$_.IPAddress -eq $configuredHost } | Select-Object -First 1)
        if ($selected.Count -ne 1) {
            throw "LanAdvertisedHost=$configuredHost 不属于已连接的有效物理网络适配器；请检查 IP、网卡状态，或移除虚拟网卡地址。"
        }
        $selected = $selected[0]
    } else {
        if ($Candidates.Count -eq 0) { throw '未发现有效私有 IPv4。请连接网络后重试，或在 config.local.ps1 中显式设置 LanAdvertisedHost。' }
        if ($Candidates.Count -gt 1) {
            $available = @($Candidates | ForEach-Object { "$($_.IPAddress)（$($_.InterfaceAlias)）" }) -join '；'
            throw "发现多个有效私有 IPv4：$available。为避免猜测，请在 config.local.ps1 中明确设置 LanAdvertisedHost。"
        }
        $selected = $Candidates[0]
    }
    if ($null -eq $NetworkProfile) { $NetworkProfile = Get-LanNetworkProfile $selected }
    if (-not $SkipPublicNetworkGuard) { Assert-LanNetworkSafety $Config $NetworkProfile }

    $lanConfig = @{}
    foreach ($entry in $Config.GetEnumerator()) { $lanConfig[$entry.Key] = $entry.Value }
    $lanConfig.LanMode = $true
    $lanConfig.LanAdvertisedHost = [string]$selected.IPAddress
    $lanConfig.BindAddress = '0.0.0.0'
    $lanConfig.CustomerWebUrl = "http://$($lanConfig.LanAdvertisedHost):$($lanConfig.CustomerWebPort)/"
    $lanConfig.LocalCustomerWebUrl = "http://127.0.0.1:$($lanConfig.CustomerWebPort)/"
    $lanConfig.LanNetworkProfile = $NetworkProfile
    $lanConfig.LanCorsAllowedOrigins = Get-LanCorsAllowedOrigins $lanConfig
    return $lanConfig
}

function Get-LanServiceListenerAddress($Config, [int]$Port) { "$($Config.BindAddress):$Port" }

function Get-LanPlatformEnvironment($Config) {
    return @{
        DATABASE_URL = [string]$Config.PlatformDatabaseUrl
        CORS_ALLOWED_ORIGINS = [string]$Config.LanCorsAllowedOrigins
    }
}

function Get-LanRagEnvironment($Config) {
    return @{
        CORS_ALLOWED_ORIGINS = [string]$Config.LanCorsAllowedOrigins
        LLM_PROVIDER = 'ollama'
        LLM_MODEL = [string]$Config.OllamaModel
        LLM_BASE_URL = [string]$Config.OllamaBaseUrl
        PLATFORM_API_BASE_URL = "http://127.0.0.1:$($Config.PlatformPort)"
    }
}

function Get-LanFrontendEnvironment($Config) {
    return @{
        VITE_RAG_API_BASE_URL = "http://$($Config.LanAdvertisedHost):$($Config.RagPort)"
        VITE_PLATFORM_API_BASE_URL = "http://$($Config.LanAdvertisedHost):$($Config.PlatformPort)"
    }
}

function Invoke-WithProcessEnvironment([hashtable]$Environment, [scriptblock]$Action) {
    $previous = @{}
    try {
        foreach ($environmentVariableName in $Environment.Keys) {
            if ($environmentVariableName -notmatch '^[A-Z_][A-Z0-9_]*$') { throw "非法环境变量名：$environmentVariableName" }
            $previous[$environmentVariableName] = [Environment]::GetEnvironmentVariable($environmentVariableName, 'Process')
            [Environment]::SetEnvironmentVariable($environmentVariableName, [string]$Environment[$environmentVariableName], 'Process')
        }
        & $Action
    } finally {
        foreach ($environmentVariableName in $Environment.Keys) { [Environment]::SetEnvironmentVariable($environmentVariableName, $previous[$environmentVariableName], 'Process') }
    }
}

function Start-ManagedServiceWithEnvironment($Config, [string]$Name, [string]$ExecutablePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$CommandFeature, [int]$Port, [hashtable]$Environment) {
    $serviceName = $Name
    $serviceExecutablePath = $ExecutablePath
    $serviceArguments = @($Arguments)
    $serviceWorkingDirectory = $WorkingDirectory
    $serviceCommandFeature = $CommandFeature
    $servicePort = $Port
    return Invoke-WithProcessEnvironment -Environment $Environment -Action {
        Start-ManagedService -Config $Config -Name $serviceName -ExecutablePath $serviceExecutablePath -Arguments $serviceArguments -WorkingDirectory $serviceWorkingDirectory -CommandFeature $serviceCommandFeature -Port $servicePort
    }
}

function Get-LanFirewallStatusMessage($NetworkProfile) {
    $profileName = switch ([string]$NetworkProfile.NetworkCategory) {
        'DomainAuthenticated' { 'Domain' }
        'Private' { 'Private' }
        'Public' { 'Public' }
        default { '' }
    }
    if ([string]::IsNullOrWhiteSpace($profileName)) {
        return 'Windows 防火墙状态：无法按当前网络类型确认；它仍可能阻断来自笔记本的访问。脚本未修改任何规则。'
    }
    try {
        $profile = Get-NetFirewallProfile -Profile $profileName -ErrorAction Stop
        if (-not [bool]$profile.Enabled) { return "Windows 防火墙状态：$profileName 配置文件已关闭（脚本未作任何修改）。" }
        return "Windows 防火墙状态：$profileName 配置文件已启用，可能阻断笔记本对 5173、8000、8011 的入站访问；脚本未创建规则。仅在受控网络上手动配置 Private 规则。"
    } catch {
        return "Windows 防火墙状态：无法读取 $profileName 配置文件（$($_.Exception.Message)）；它仍可能阻断笔记本访问。脚本未修改任何规则。"
    }
}

function Get-ProcessMetadata([int]$Id) {
    Get-CimInstance Win32_Process -Filter "ProcessId = $Id" -ErrorAction SilentlyContinue
}

function Test-RecordedProcess($Config, [string]$Name, [switch]$Detailed) {
    $path = Get-ServiceRecordPath $Config $Name
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return [pscustomobject]@{ Valid = $false; Reason = '运行记录无法解析'; Record = $null; Process = $null } }
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return [pscustomobject]@{ Valid = $false; Reason = 'PID 已退出'; Record = $record; Process = $null } }
    $metadata = Get-ProcessMetadata $process.Id
    $actualExecutablePath = if ($metadata -and -not [string]::IsNullOrWhiteSpace($metadata.ExecutablePath)) { [string]$metadata.ExecutablePath } else { [string]$process.Path }
    if ([string]::IsNullOrWhiteSpace($actualExecutablePath)) { return [pscustomobject]@{ Valid = $false; Reason = '无法读取进程可执行路径'; Record = $record; Process = $process } }
    $sameExecutable = [string]::Equals([IO.Path]::GetFullPath($actualExecutablePath), [IO.Path]::GetFullPath($record.executablePath), [StringComparison]::OrdinalIgnoreCase)
    $canVerifyCommandLine = $metadata -and -not [string]::IsNullOrWhiteSpace($metadata.CommandLine)
    $hasFeature = $canVerifyCommandLine -and $metadata.CommandLine.IndexOf([string]$record.commandFeature, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $recordedStart = ([datetime]$record.startedUtc).ToUniversalTime().ToString('o')
    $sameStart = $process.StartTime.ToUniversalTime().ToString('o') -eq $recordedStart
    if ($sameExecutable -and $sameStart -and ($hasFeature -or -not $canVerifyCommandLine)) {
        $reason = if ($hasFeature) { '已验证' } else { '已验证（系统未公开命令行，使用可执行路径和启动时间）' }
        return [pscustomobject]@{ Valid = $true; Reason = $reason; Record = $record; Process = $process }
    }
    return [pscustomobject]@{ Valid = $false; Reason = 'PID、可执行路径、启动时间或命令特征不匹配'; Record = $record; Process = $process }
}

function Save-ServiceRecord($Config, [string]$Name, $Process, [string]$ExecutablePath, [string]$WorkingDirectory, [string]$CommandSummary, [string]$CommandFeature, [int]$Port) {
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory, (Get-ServiceLogDirectory $Config) | Out-Null
    $record = [ordered]@{ name=$Name; pid=$Process.Id; executablePath=[IO.Path]::GetFullPath($ExecutablePath); workingDirectory=[IO.Path]::GetFullPath($WorkingDirectory); startedUtc=$Process.StartTime.ToUniversalTime().ToString('o'); commandSummary=$CommandSummary; commandFeature=$CommandFeature; port=$Port; logDirectory=(Get-ServiceLogDirectory $Config) }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Get-ServiceRecordPath $Config $Name) -Encoding UTF8
}

function Get-PortOwner([int]$Port) {
    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -gt 0) { return $owners }
    $netstat = Join-Path $env:SystemRoot 'System32\netstat.exe'
    $pattern = '^\s*TCP\s+\S+:' + [regex]::Escape([string]$Port) + '\s+\S+\s+LISTENING\s+(\d+)\s*$'
    return @(& $netstat -ano -p tcp 2>$null | Where-Object { $_ -match $pattern } | ForEach-Object { [int]$Matches[1] } | Select-Object -Unique)
}
function Assert-PortAvailable($Config, [string]$Name, [int]$Port) {
    $owners = @(Get-PortOwner $Port)
    if ($owners.Count -eq 0) { return }
    $record = Test-RecordedProcess $Config $Name
    if ($record -and $record.Valid -and $owners -contains $record.Process.Id) { throw "$Name 已由本工具启动（PID $($record.Process.Id)，端口 $Port）。请使用检查脚本，或先停止后再启动。" }
    throw "端口 $Port 已被未知或未验证进程占用（PID：$($owners -join ', ')）。为避免误杀，启动已停止；请人工处理该进程。"
}

function Test-HttpOk([string]$Url) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3; return $r.StatusCode -ge 200 -and $r.StatusCode -lt 400 } catch { return $false } }
function Wait-HttpOk([string]$Url, [int]$Seconds, [string]$Label) { for ($i=0; $i -lt $Seconds; $i++) { if (Test-HttpOk $Url) { return }; Start-Sleep -Seconds 1 }; throw "$Label 未在 $Seconds 秒内就绪：$Url。请查看运行日志。" }

function Get-Json([string]$Url, [string]$Label) {
    try { return Invoke-RestMethod -UseBasicParsing -Uri $Url -TimeoutSec 10 } catch { throw "$Label 请求失败：$Url。$($_.Exception.Message)" }
}

function Assert-OllamaReady($Config) {
    $tags = Get-Json "$($Config.OllamaBaseUrl)/api/tags" 'Ollama'
    $model = @($tags.models | Where-Object { [string]$_.name -eq [string]$Config.OllamaModel })
    if ($model.Count -ne 1) { throw "Ollama 模型不存在：$($Config.OllamaModel)。脚本不会下载模型。" }
    return $tags
}

function Invoke-PlatformMigration($Config) {
    $platformDirectory = Join-Path $Config.RepositoryRoot 'platform_backend'
    Push-Location -LiteralPath $platformDirectory
    try {
        & $Config.PlatformPythonPath -m alembic upgrade head
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) { throw "C 数据库迁移失败（退出码 $exitCode）；不会启动 C。" }
}

function Get-PlatformMigrationStatus($Config) {
    $platformDirectory = Join-Path $Config.RepositoryRoot 'platform_backend'
    $code = "from sqlalchemy import create_engine, text; from app.config import get_settings; engine = create_engine(get_settings().database_url); print(engine.connect().execute(text('select version_num from alembic_version')).scalar_one())"
    Push-Location -LiteralPath $platformDirectory
    try {
        $revision = & $Config.PlatformPythonPath -c $code 2>$null
        $exitCode = $LASTEXITCODE
    } catch {
        return "未迁移（$($_.Exception.Message)）"
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace([string]$revision)) { return '未迁移或无法读取 alembic_version' }
    return "已迁移（revision $($revision | Select-Object -Last 1)）"
}

function Get-ServiceStatus($Config, [string]$Name, [int]$Port, [string]$HealthUrl) {
    $record = Test-RecordedProcess $Config $Name
    $serviceProcessId = if ($record -and $record.Process) { $record.Process.Id } else { '-' }
    $serviceState = if ($record -and $record.Valid) { '运行中' } else { '未运行' }
    $portOwners = @(Get-PortOwner $Port)
    $healthOk = Test-HttpOk $HealthUrl
    $portState = if ($portOwners.Count -gt 0) { "监听（PID $($portOwners -join ', ')）" } elseif ($healthOk) { '监听（health 已确认；未能读取端口 PID）' } else { '未监听' }
    $healthState = if ($healthOk) { '可用' } else { '不可用' }
    return [pscustomobject]@{ Name=$Name; State=$serviceState; ProcessId=$serviceProcessId; Port=$Port; PortState=$portState; HealthState=$healthState; Record=$record }
}

function Assert-Dependencies($Config) {
    foreach ($item in @(@{Name='RAG Python';Path=$Config.RagPythonPath}, @{Name='平台 Python';Path=$Config.PlatformPythonPath})) { & $item.Path --version | Out-Null; if ($LASTEXITCODE -ne 0) { throw "$($item.Name) 无法执行：$($item.Path)" } }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue; if (-not $node) { throw '缺少 Node.js（node.exe）。脚本不会自动安装。' }
    & $Config.PnpmCommand --version | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'pnpm 无法执行。脚本不会自动安装依赖。' }
    Assert-OllamaReady $Config | Out-Null
    foreach ($path in @((Join-Path $Config.RepositoryRoot 'backend\.venv\Scripts\python.exe'), (Join-Path $Config.RepositoryRoot 'platform_backend\.venv\Scripts\python.exe'), (Join-Path $Config.RepositoryRoot 'frontend\node_modules'))) { if (-not (Test-Path -LiteralPath $path)) { throw "缺少预先安装的运行依赖：$path" } }
    if (-not (Test-Path -LiteralPath (Join-Path $Config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'))) { throw 'frontend node_modules 中缺少 Vite。请人工安装依赖。' }
}

function Assert-RagVirtualEnvironment($Config) {
    $ragVenvPython = Join-Path $Config.RepositoryRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $ragVenvPython)) {
        throw "A .venv 缺失：$ragVenvPython。脚本不会自动安装依赖。"
    }
}

function Write-StartupFailureSummary($Config, [string[]]$StartedServices) {
    Write-Host '启动失败；本次启动流程服务状态：' -ForegroundColor Yellow
    foreach ($service in @(@{ Label='C'; Name='platform' }, @{ Label='A'; Name='rag' }, @{ Label='B'; Name='customer-web' })) {
        $state = if ($StartedServices -contains $service.Name) { '已启动' } else { '未启动' }
        Write-Host "$($service.Label)：$state"
    }
}

function Normalize-ProcessPathEnvironment {
    $environment = [Environment]::GetEnvironmentVariables('Process')
    $pathKeys = @($environment.Keys | Where-Object { [string]$_ -match '^path$' })
    if ($pathKeys.Count -le 1) { return }
    $pathValue = [Environment]::GetEnvironmentVariable('Path', 'Process')
    if ([string]::IsNullOrWhiteSpace($pathValue)) { $pathValue = [Environment]::GetEnvironmentVariable([string]$pathKeys[0], 'Process') }
    [Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable('Path', $pathValue, 'Process')
}

function Start-ManagedService($Config, [string]$Name, [string]$ExecutablePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$CommandFeature, [int]$Port) {
    Assert-PortAvailable $Config $Name $Port
    $logDir = Get-ServiceLogDirectory $Config
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory, $logDir | Out-Null
    Normalize-ProcessPathEnvironment
    $process = Start-Process -FilePath $ExecutablePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput (Join-Path $logDir "$Name.out.log") -RedirectStandardError (Join-Path $logDir "$Name.err.log") -WindowStyle Hidden -PassThru
    Save-ServiceRecord $Config $Name $process $ExecutablePath $WorkingDirectory (($Arguments -join ' ')) $CommandFeature $Port
    return $process
}

function Stop-ManagedService($Config, [string]$Name) {
    $path = Get-ServiceRecordPath $Config $Name
    if (-not (Test-Path -LiteralPath $path)) { Write-Host "$Name：没有本工具的运行记录。"; return }
    $check = Test-RecordedProcess $Config $Name
    if (-not $check.Process) { Remove-Item -LiteralPath $path -Force; Write-Host "$Name：记录的进程已退出，已清理记录。"; return }
    if (-not $check.Valid) { Write-Warning "$Name：拒绝停止 PID $($check.Process.Id)，原因：$($check.Reason)。请人工核对后处理。"; return }
    Stop-Process -Id $check.Process.Id -ErrorAction Stop
    Start-Sleep -Milliseconds 500
    if (Get-Process -Id $check.Process.Id -ErrorAction SilentlyContinue) { throw "$Name（PID $($check.Process.Id)）未能停止，请人工处理。" }
    Remove-Item -LiteralPath $path -Force
    Write-Host "$Name 已停止（PID $($check.Record.pid)）。"
}

function Get-NormalizedTestDataPackagePath($Config) {
    if ([string]::IsNullOrWhiteSpace([string]$Config.TestDataPackagePath) -or -not (Test-Path -LiteralPath $Config.TestDataPackagePath)) { throw 'AutoImportTestData=true 时，TestDataPackagePath 必须指向存在的 ZIP 测试数据包。' }
    $sourcePath = (Resolve-Path -LiteralPath $Config.TestDataPackagePath -ErrorAction Stop).Path
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($sourcePath)
    try {
        $rootManifest = @($archive.Entries | Where-Object { $_.FullName -eq 'manifest.json' })
        if ($rootManifest.Count -eq 1) { return $sourcePath }
        $manifests = @($archive.Entries | Where-Object { $_.FullName -match '^[^/]+/manifest\.json$' })
        if ($manifests.Count -ne 1) { throw '测试 ZIP 未在根目录包含 manifest.json，且不能安全识别单一顶层目录。' }
        $prefix = $manifests[0].FullName.Substring(0, $manifests[0].FullName.Length - 'manifest.json'.Length)
        $filesOutsidePrefix = @($archive.Entries | Where-Object { $_.Length -gt 0 -and -not $_.FullName.StartsWith($prefix, [StringComparison]::Ordinal) })
        if ($filesOutsidePrefix.Count -gt 0) { throw '测试 ZIP 含有顶层目录以外的文件，拒绝生成标准化副本。' }
        $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $packageDirectory = Join-Path $Config.RuntimeDirectory 'test-packages'
        New-Item -ItemType Directory -Force -Path $packageDirectory | Out-Null
        $targetPath = Join-Path $packageDirectory "normalized-$sourceHash.zip"
        if (Test-Path -LiteralPath $targetPath) { return $targetPath }
        $temporaryPath = Join-Path $packageDirectory ("normalized-$sourceHash-" + [Guid]::NewGuid().ToString('N') + '.tmp')
        try {
            $normalized = [IO.Compression.ZipFile]::Open($temporaryPath, [IO.Compression.ZipArchiveMode]::Create)
            try {
                foreach ($entry in $archive.Entries | Where-Object { $_.Length -gt 0 }) {
                    $relativeName = $entry.FullName.Substring($prefix.Length)
                    if ([string]::IsNullOrWhiteSpace($relativeName) -or $relativeName.StartsWith('/') -or $relativeName -match '(^|/)\.\.(/|$)') { throw "测试 ZIP 内存在不安全的标准化路径：$($entry.FullName)" }
                    $destination = $normalized.CreateEntry($relativeName, [IO.Compression.CompressionLevel]::Optimal)
                    $input = $entry.Open(); $output = $destination.Open()
                    try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose() }
                }
            } finally {
                $normalized.Dispose()
            }
            if (Test-Path -LiteralPath $targetPath) { Remove-Item -LiteralPath $temporaryPath -Force } else { Move-Item -LiteralPath $temporaryPath -Destination $targetPath }
        } catch {
            if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
            throw
        }
        Write-Host "已在运行目录生成临时标准化测试 ZIP：$targetPath"
        return $targetPath
    } finally {
        $archive.Dispose()
    }
}

function Invoke-TestPackageUpload([string]$Url, [string]$Path, [string]$Label) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $form = New-Object System.Net.Http.MultipartFormDataContent
    $stream = [IO.File]::OpenRead($Path)
    try {
        $content = New-Object System.Net.Http.StreamContent($stream)
        $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/zip')
        $form.Add($content, 'file', [IO.Path]::GetFileName($Path))
        $response = $client.PostAsync($Url, $form).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) { throw "$Label 失败：HTTP $([int]$response.StatusCode) $body" }
        try { return $body | ConvertFrom-Json } catch { throw "$Label 返回的不是 JSON。" }
    } finally {
        $stream.Dispose(); $form.Dispose(); $client.Dispose()
    }
}

function Get-TestDataPackage($Config) {
    $packages = Get-Json (Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-data-packages') 'C 测试包列表'
    return @($packages.items | Where-Object { [string]$_.package_id -eq [string]$Config.TestKnowledgePackageId } | Select-Object -First 1)
}

function Import-TestDataPackage($Config) {
    $existing = @(Get-TestDataPackage $Config)
    if ($existing.Count -eq 1) { Write-Host "测试包 $($Config.TestKnowledgePackageId) 已存在，跳过重复导入。"; return $existing[0] }
    if (-not [bool]$Config.AutoImportTestData) { throw "测试包 $($Config.TestKnowledgePackageId) 不存在。请配置 TestDataPackagePath 并将 AutoImportTestData 设为 `$true。" }
    $uploadPath = Get-NormalizedTestDataPackagePath $Config
    $preflight = Invoke-TestPackageUpload (Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-data-packages/preflight') $uploadPath '测试数据包预检'
    if (-not [bool]$preflight.can_import -or [string]$preflight.package_id -ne [string]$Config.TestKnowledgePackageId) { throw "测试数据包预检不通过或 package_id 不匹配：$($Config.TestKnowledgePackageId)" }
    $imported = Invoke-TestPackageUpload (Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-data-packages') $uploadPath '测试数据包导入'
    if ([string]$imported.package_id -ne [string]$Config.TestKnowledgePackageId) { throw "测试数据包导入后的 package_id 不匹配：$($imported.package_id)" }
    Write-Host "测试包 $($Config.TestKnowledgePackageId) 已导入。"
    return $imported
}

function Get-TestKnowledgeSyncRecordPath($Config) { Join-Path $Config.RuntimeDirectory 'test-knowledge-sync.json' }

function Sync-TestKnowledge($Config) {
    if (-not [bool]$Config.AutoSyncTestKnowledge) { Write-Host 'AutoSyncTestKnowledge=false，跳过 A 测试知识同步。'; return $null }
    $response = Invoke-RestMethod -UseBasicParsing -Method Post -Uri (Get-ServiceUrl $Config $Config.RagPort "/api/test-knowledge/sync/$($Config.TestKnowledgePackageId)") -TimeoutSec 120
    $data = if ($response.data) { $response.data } else { $response }
    if ([int]$data.synced_items -ne 47 -or [int]$data.collection_count -ne 47) { throw "A 测试知识同步数量异常：synced_items=$($data.synced_items)，collection_count=$($data.collection_count)，期望均为 47。" }
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory | Out-Null
    [ordered]@{ packageId=$Config.TestKnowledgePackageId; syncedItems=[int]$data.synced_items; collectionCount=[int]$data.collection_count; verifiedUtc=[datetime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Get-TestKnowledgeSyncRecordPath $Config) -Encoding UTF8
    Write-Host 'A 测试知识同步完成：47 条。'
    return $data
}

function Assert-RagRuntimeReady($Config) {
    $status = Get-Json (Get-ServiceUrl $Config $Config.RagPort '/api/status') 'A 状态'
    if (-not [bool]$status.ready -or -not [bool]$status.model_configured -or $null -ne $status.initialization_error) {
        throw "A 状态校验失败：ready=$($status.ready)，model_configured=$($status.model_configured)，initialization_error=$($status.initialization_error)。不会启动 B。"
    }
    return $status
}

function Wait-RagRuntimeReady($Config, [int]$Seconds) {
    $lastStatus = $null
    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            $lastStatus = Get-Json (Get-ServiceUrl $Config $Config.RagPort '/api/status') 'A 状态'
            if ([bool]$lastStatus.ready -and [bool]$lastStatus.model_configured -and $null -eq $lastStatus.initialization_error) { return $lastStatus }
        } catch {
            $lastStatus = $null
        }
        Start-Sleep -Seconds 1
    }
    if ($null -eq $lastStatus) { throw "A 未在 $Seconds 秒内返回可验证状态；不会启动 B。" }
    throw "A 未在 $Seconds 秒内就绪：ready=$($lastStatus.ready)，model_configured=$($lastStatus.model_configured)，initialization_error=$($lastStatus.initialization_error)。不会启动 B。"
}

function Invoke-RagChatSmoke($Config) {
    $stores = Get-Json (Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-catalog/stores') 'C 店铺列表'
    $store = @($stores.items | Select-Object -First 1)[0]
    if ($null -eq $store) { throw 'C 没有可供聊天 smoke 使用的测试店铺。' }
    $products = Get-Json ((Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-catalog/products') + '?store_code=' + [uri]::EscapeDataString([string]$store.store_code)) 'C 商品列表'
    $product = @($products.items | Select-Object -First 1)[0]
    if ($null -eq $product) { throw 'C 没有可供聊天 smoke 使用的测试商品。' }
    $skus = Get-Json (Get-ServiceUrl $Config $Config.PlatformPort "/api/v1/test-catalog/products/$([uri]::EscapeDataString([string]$product.product_id))/skus") 'C SKU 列表'
    $sku = @($skus.items | Select-Object -First 1)[0]
    $payload = @{ question='请根据当前商品资料介绍适用年龄和安全注意事项。'; context=@{ tenant_id=[string]$store.tenant_id; platform=[string]$store.platform; store_code=[string]$store.store_code; product_id=[string]$product.product_id; sku_id=if ($sku) { [string]$sku.sku_id } else { $null } } } | ConvertTo-Json -Depth 5
    try { $response = Invoke-RestMethod -UseBasicParsing -Method Post -ContentType 'application/json; charset=utf-8' -Body $payload -Uri (Get-ServiceUrl $Config $Config.RagPort '/api/chat') -TimeoutSec 120 } catch { throw "A 真实聊天 smoke 失败：$($_.Exception.Message)" }
    $data = if ($response.data) { $response.data } else { $response }
    $answer = [string]$data.answer
    if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '大模型尚未配置|大模型请求失败|NO_SCOPED_KNOWLEDGE' -or @($data.sources).Count -eq 0) { throw "A 真实聊天 smoke 未得到可用 Ollama 回答：$answer" }
    Write-Host 'A 真实 Ollama chat smoke 通过。'
    return $data
}
