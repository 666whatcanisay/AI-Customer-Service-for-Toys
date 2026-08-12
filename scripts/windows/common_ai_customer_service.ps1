Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-AiCustomerServiceConfigPath([string]$ConfigPath, [string]$ScriptRoot = $PSScriptRoot) {
    if (-not [string]::IsNullOrWhiteSpace($ConfigPath)) { return $ConfigPath }
    $repositoryRoot = [IO.Path]::GetFullPath((Join-Path $ScriptRoot '..\..'))
    $standardRuntimeConfigPath = Join-Path $repositoryRoot '.runtime\phase-e\config\green-standard.local.ps1'
    if (Test-Path -LiteralPath $standardRuntimeConfigPath -PathType Leaf) { return $standardRuntimeConfigPath }
    $legacyConfigPath = Join-Path $ScriptRoot 'config.local.ps1'
    if (Test-Path -LiteralPath $legacyConfigPath -PathType Leaf) { return $legacyConfigPath }
    return $legacyConfigPath
}

function Assert-AiCsCanonicalRuntimeSource(
    $Config,
    [string]$ResolvedConfigPath,
    [switch]$RequireCanonicalRoot,
    [string]$EntryRepositoryRootOverride = ''
) {
    if (-not $RequireCanonicalRoot) { return }
    $repositoryRoot = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
    $repositoryName = Split-Path -Leaf $repositoryRoot
    if (-not [string]::Equals($repositoryName, 'AI-CS', [StringComparison]::OrdinalIgnoreCase)) {
        throw '检测到旧项目路径，请使用迁移后的AI-CS目录。'
    }

    $entryRepositoryRoot = if ([string]::IsNullOrWhiteSpace($EntryRepositoryRootOverride)) {
        [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    } else {
        [IO.Path]::GetFullPath($EntryRepositoryRootOverride)
    }
    if (-not [string]::Equals((Split-Path -Leaf $entryRepositoryRoot), 'AI-CS', [StringComparison]::OrdinalIgnoreCase)) {
        throw "检测到旧项目路径，请使用迁移后的AI-CS目录：$entryRepositoryRoot"
    }
    if (-not [string]::Equals($repositoryRoot, $entryRepositoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime配置的RepositoryRoot不是当前AI-CS目录：$repositoryRoot"
    }
    $expectedConfigPath = [IO.Path]::GetFullPath((Join-Path $entryRepositoryRoot '.runtime\phase-e\config\green-standard.local.ps1'))
    try { $actualConfigPath = (Resolve-Path -LiteralPath $ResolvedConfigPath -ErrorAction Stop).Path } catch { throw "Runtime配置不存在：$ResolvedConfigPath" }
    if (-not [string]::Equals($actualConfigPath, $expectedConfigPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "标准Runtime必须使用green-standard.local.ps1：$expectedConfigPath"
    }
}

function Write-AiCsStartupPreflight($Config, [string]$ResolvedConfigPath) {
    $identity = Get-RepositoryRuntimeIdentity ([string]$Config.RepositoryRoot)
    if (-not $identity.Available) { throw "无法读取启动Git身份：$($identity.Reason)" }
    if ([string]$identity.SourceState -ne 'CLEAN') { throw '正式AI-CS工作区不是CLEAN，拒绝启动。请先确认并提交受控修改。' }

    $ragVersion = [string](& $Config.RagPythonPath --version 2>&1 | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0) { throw "A Python环境不可用：$($Config.RagPythonPath)" }
    $platformVersion = [string](& $Config.PlatformPythonPath --version 2>&1 | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0) { throw "C Python环境不可用：$($Config.PlatformPythonPath)" }
    Write-Host "启动预检：Repository=$($identity.RepositoryRoot)" -ForegroundColor Cyan
    Write-Host "启动预检：SHA=$($identity.GitSha)；Source=$($identity.SourceState)"
    Write-Host "启动预检：Config=$([IO.Path]::GetFullPath($ResolvedConfigPath))"
    Write-Host "启动预检：A Python=$ragVersion；C Python=$platformVersion；Web=prebuilt-static"
}

function Get-LocalConfig([string]$ConfigPath) {
    $configPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "缺少本地配置：$configPath。可显式传入 -ConfigPath，或为正式 AI-CS 准备 .runtime\phase-e\config\green-standard.local.ps1。"
    }
    $config = & $configPath
    if ($null -eq $config -or -not ($config -is [hashtable])) { throw 'config.local.ps1 必须返回一个 hashtable（请以示例文件为准）。' }
    $optionalDefaults = [ordered]@{
        # RuntimeMode identifies the deployment role. Network exposure is
        # recorded separately as network_mode and must not redefine identity.
        RuntimeMode = 'standard'
        GatewayEnabled = $false
        GatewayClientId = 'channel-engine'
        GatewayKeyId = 'gateway-key-v1'
        GatewaySecretReference = ''
        # Independent A/C service credential. Never reuse the Gateway HMAC key.
        InternalServiceSecretReference = ''
        # LAN customer Web must terminate TLS with runtime-managed file references.
        CustomerWebTlsCertificateReference = ''
        CustomerWebTlsKeyReference = ''
        GatewayStatePath = ''
        GatewayClockSkewSeconds = 300
        GatewayNonceTtlSeconds = 600
        GatewayDecisionRetentionSeconds = 604800
        GatewayDecisionLeaseSeconds = 30
        # The Core stays on loopback. LAN mode uses a separate allowlisted edge.
        GatewayLanBindAddress = 'auto'
        GatewayLanPort = 18080
        GatewayAllowedNetworks = @('auto')
        GatewayUpstreamTimeoutSeconds = 180
        # Customer Desktop Workflow is opt-in. C reads only an external opaque
        # Channel Engine operator session reference; never place it in config.
        ChannelAgentIntegrationEnabled = $false
        ChannelAgentServerUrl = ''
        ChannelAgentOperatorSessionReference = ''
        ChannelAgentTimeoutSeconds = 5
        OllamaBaseUrl = 'http://127.0.0.1:11434'
        # No database default: a missing production path must fail closed.
        PlatformDatabaseUrl = ''
        PlatformDatabaseBindingPath = ''
        PlatformDatabaseEnvironmentId = ''
        PlatformRequireDatabaseIdentity = $true
        # Acceptance knowledge belongs to an explicit bootstrap command.
        TestKnowledgePackageId = ''
        AutoSyncTestKnowledge = $false
        RagPrimaryCollectionName = 'documents'
        RagActiveCollectionName = 'test_knowledge_v031'
        # The dedicated LAN launcher always resolves this value again at startup.
        # 'auto' prevents a stale hotspot or office address from being reused.
        LanAddress = 'auto'
        PreferredInterfaceAlias = ''
        EnableLanMode = $false
        # Legacy keys remain readable so older ignored local files do not fail.
        LanMode = $false
        LanBindAddress = '0.0.0.0'
        LanAdvertisedHost = ''
        AllowPublicNetwork = $false
        # The management UI remains loopback-only unless an operator explicitly
        # opts into LAN exposure. This launcher never changes firewall rules.
        AdminWebPort = 5174
        AdminWebBindAddress = '127.0.0.1'
        AdminWebUrl = 'http://127.0.0.1:5174/'
        AdminEnableLanMode = $false
        AdminOpenBrowser = $false
    }
    foreach ($entry in $optionalDefaults.GetEnumerator()) {
        if (-not $config.ContainsKey($entry.Key) -or $null -eq $config[$entry.Key] -or [string]::IsNullOrWhiteSpace([string]$config[$entry.Key])) {
            $config[$entry.Key] = $entry.Value
        }
    }
    foreach ($key in @('RepositoryRoot','RagPythonPath','PlatformPythonPath','RagPort','CustomerWebPort','PlatformPort','BindAddress','CustomerWebUrl','RagHealthPath','PlatformHealthPath','OllamaModel','CorsAllowedOrigins','OpenBrowser','RuntimeDirectory','AutoImportTestData')) {
        if (-not $config.ContainsKey($key) -or $null -eq $config[$key] -or [string]::IsNullOrWhiteSpace([string]$config[$key])) { throw "配置项 $key 缺失或为空。" }
    }
    try { $root = (Resolve-Path -LiteralPath $config.RepositoryRoot -ErrorAction Stop).Path } catch { throw "RepositoryRoot 不存在：$($config.RepositoryRoot)" }
    foreach ($directory in @('backend','frontend','platform_backend')) { if (-not (Test-Path -LiteralPath (Join-Path $root $directory))) { throw "RepositoryRoot 不含 $directory：$root" } }
    $config.RepositoryRoot = $root
    if ([string]::IsNullOrWhiteSpace([string]$config.RuntimeDirectory)) { $config.RuntimeDirectory = Join-Path $root '.runtime' }
    $runtimePathDefaults = [ordered]@{
        RagKnowledgeBasePath = (Join-Path $root 'backend\knowledge_base')
        RagVectorDbPath = (Join-Path $root 'backend\vector_db')
        RagLogDirectory = (Join-Path $root 'logs')
        PlatformKnowledgeMaterialStorageDirectory = (Join-Path $root 'platform_backend\.runtime\knowledge-materials')
    }
    $rootPrefix = $root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    foreach ($entry in $runtimePathDefaults.GetEnumerator()) {
        $configuredPath = if (-not $config.ContainsKey($entry.Key) -or [string]::IsNullOrWhiteSpace([string]$config[$entry.Key])) { [string]$entry.Value } else { [string]$config[$entry.Key] }
        $fullPath = if ([IO.Path]::IsPathRooted($configuredPath)) { [IO.Path]::GetFullPath($configuredPath) } else { [IO.Path]::GetFullPath((Join-Path $root $configuredPath)) }
        if ($fullPath -ne $root -and -not $fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "$($entry.Key) 必须位于 RepositoryRoot 内：$fullPath" }
        $config[$entry.Key] = $fullPath
    }
    foreach ($key in @('RagPrimaryCollectionName','RagActiveCollectionName')) {
        $value = [string]$config[$key]
        if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\r\n]') { throw "配置项 $key 必须是单行非空 Collection 名称。" }
        $config[$key] = $value.Trim()
    }
    $runtimeMode = ([string]$config.RuntimeMode).Trim().ToLowerInvariant()
    if ($runtimeMode -notin @('standard', 'shadow', 'recovery')) {
        throw 'RuntimeMode 只允许 standard、shadow 或 recovery。'
    }
    $config.RuntimeMode = $runtimeMode
    foreach ($name in @('RagPort','CustomerWebPort','PlatformPort','AdminWebPort','GatewayLanPort')) {
        $port = 0
        if (-not [int]::TryParse([string]$config[$name], [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw "$name 必须为 1-65535 的端口。" }
        $config[$name] = $port
    }
    if ((@($config.RagPort,$config.CustomerWebPort,$config.PlatformPort,$config.AdminWebPort,$config.GatewayLanPort) | Select-Object -Unique).Count -ne 5) { throw '五个受管服务端口必须不同。' }
    foreach ($pathKey in @('RagPythonPath','PlatformPythonPath')) { if (-not (Test-Path -LiteralPath $config[$pathKey])) { throw "$pathKey 不存在：$($config[$pathKey])" } }
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
    foreach ($key in @('PlatformDatabaseUrl', 'PlatformDatabaseBindingPath', 'PlatformDatabaseEnvironmentId')) {
        if ([string]::IsNullOrWhiteSpace([string]$config[$key])) { throw "配置项 $key 缺失或为空。" }
    }
    $databaseUri = $null
    if (-not [uri]::TryCreate([string]$config.PlatformDatabaseUrl, [UriKind]::Absolute, [ref]$databaseUri) -or $databaseUri.Scheme -ne 'sqlite') {
        throw 'PlatformDatabaseUrl 必须是指向绝对路径的 sqlite URL。'
    }
    $databasePath = [uri]::UnescapeDataString($databaseUri.AbsolutePath)
    if ($databasePath -match '^/[A-Za-z]:/') { $databasePath = $databasePath.Substring(1) }
    $databasePath = $databasePath.Replace('/', [IO.Path]::DirectorySeparatorChar)
    if (-not [IO.Path]::IsPathRooted($databasePath)) { throw 'PlatformDatabaseUrl 禁止相对路径。' }
    $config.PlatformDatabasePath = [IO.Path]::GetFullPath($databasePath)
    $config.PlatformDatabaseBindingPath = [IO.Path]::GetFullPath([string]$config.PlatformDatabaseBindingPath)
    if ([string]$config.PlatformDatabaseEnvironmentId -notmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$') { throw 'PlatformDatabaseEnvironmentId 格式无效。' }
    try {
        $adminWebUri = [uri]$config.AdminWebUrl
        if (-not $adminWebUri.IsAbsoluteUri -or $adminWebUri.Scheme -notin @('http', 'https') -or [string]::IsNullOrWhiteSpace($adminWebUri.Host) -or $adminWebUri.Port -ne [int]$config.AdminWebPort) {
            throw 'invalid'
        }
        $config.AdminWebUrl = $adminWebUri.AbsoluteUri
    } catch {
        throw "AdminWebUrl 必须是与 AdminWebPort 一致的有效 http(s) 地址：$($config.AdminWebUrl)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$config.AdminWebBindAddress)) { throw 'AdminWebBindAddress 不能为空。' }
    foreach ($key in @('OpenBrowser', 'AutoImportTestData', 'AutoSyncTestKnowledge', 'PlatformRequireDatabaseIdentity', 'EnableLanMode', 'LanMode', 'AllowPublicNetwork', 'AdminEnableLanMode', 'AdminOpenBrowser', 'GatewayEnabled', 'ChannelAgentIntegrationEnabled')) {
        if ($config[$key] -isnot [bool]) {
            $parsed = $false
            if (-not [bool]::TryParse([string]$config[$key], [ref]$parsed)) { throw "配置项 $key 必须为 true 或 false。" }
            $config[$key] = $parsed
        }
    }
    if (-not [bool]$config.AdminEnableLanMode) {
        if ([string]$config.AdminWebBindAddress -notin @('127.0.0.1', '::1', 'localhost')) {
            throw 'AdminEnableLanMode=false 时 AdminWebBindAddress 必须是本机回环地址。'
        }
        if ($adminWebUri.Host -notin @('127.0.0.1', '::1', 'localhost')) {
            throw 'AdminEnableLanMode=false 时 AdminWebUrl 必须是本机回环地址。'
        }
    }
    foreach ($key in @('GatewayClockSkewSeconds','GatewayNonceTtlSeconds','GatewayDecisionRetentionSeconds','GatewayDecisionLeaseSeconds','GatewayUpstreamTimeoutSeconds')) {
        $value = 0
        if (-not [int]::TryParse([string]$config[$key], [ref]$value) -or $value -lt 1) {
            throw "$key 必须为正整数。"
        }
        $config[$key] = $value
    }
    if ([string]$config.GatewayClientId -notmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$') { throw 'GatewayClientId 格式无效。' }
    if ([string]$config.GatewayKeyId -notmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$') { throw 'GatewayKeyId 格式无效。' }
    $gatewayLanBindAddress = ([string]$config.GatewayLanBindAddress).Trim()
    if ($gatewayLanBindAddress -ne 'auto' -and -not (Test-PrivateLanIpv4 $gatewayLanBindAddress)) {
        throw 'GatewayLanBindAddress 必须为 auto 或 RFC1918 私有 IPv4；禁止通配符、回环和公网地址。'
    }
    $config.GatewayLanBindAddress = $gatewayLanBindAddress
    $gatewayAllowedNetworks = @($config.GatewayAllowedNetworks | ForEach-Object { ([string]$_).Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    if ($gatewayAllowedNetworks.Count -eq 0) { throw 'GatewayAllowedNetworks 至少需要一个私有 CIDR，或仅填写 auto。' }
    if ($gatewayAllowedNetworks -contains 'auto' -and $gatewayAllowedNetworks.Count -ne 1) { throw 'GatewayAllowedNetworks=auto 不能与显式 CIDR 混用。' }
    foreach ($network in $gatewayAllowedNetworks) {
        if ($network -ne 'auto' -and -not (Test-PrivateLanCidr $network)) { throw "GatewayAllowedNetworks 仅允许规范 RFC1918 CIDR：$network" }
    }
    $config.GatewayAllowedNetworks = $gatewayAllowedNetworks
    $runtimeDirectory = [IO.Path]::GetFullPath([string]$config.RuntimeDirectory)
    $runtimePrefix = $runtimeDirectory.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ([string]::IsNullOrWhiteSpace([string]$config.GatewayStatePath)) {
        $config.GatewayStatePath = Join-Path $runtimeDirectory 'gateway\gateway_state.sqlite3'
    } else {
        $statePath = [string]$config.GatewayStatePath
        $config.GatewayStatePath = if ([IO.Path]::IsPathRooted($statePath)) { [IO.Path]::GetFullPath($statePath) } else { [IO.Path]::GetFullPath((Join-Path $runtimeDirectory $statePath)) }
    }
    if (-not ([string]$config.GatewayStatePath).StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "GatewayStatePath 必须位于 RuntimeDirectory 内：$($config.GatewayStatePath)"
    }
    if ([bool]$config.GatewayEnabled) {
        if ([string]::IsNullOrWhiteSpace([string]$config.GatewaySecretReference)) {
            throw 'GatewayEnabled=true 时必须配置 GatewaySecretReference；禁止在配置中填写明文 secret。'
        }
        $secretReference = [string]$config.GatewaySecretReference
        $secretPath = if ([IO.Path]::IsPathRooted($secretReference)) { [IO.Path]::GetFullPath($secretReference) } else { [IO.Path]::GetFullPath((Join-Path $runtimeDirectory $secretReference)) }
        if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) { throw "GatewaySecretReference 不存在：$secretPath" }
        $config.GatewaySecretReference = $secretPath
    }
    if ([string]::IsNullOrWhiteSpace([string]$config.InternalServiceSecretReference)) {
        throw 'Production Runtime 必须配置 InternalServiceSecretReference；禁止匿名 A/C 内部调用或明文 secret。'
    }
    $internalSecretReference = [string]$config.InternalServiceSecretReference
    $internalSecretPath = if ([IO.Path]::IsPathRooted($internalSecretReference)) { [IO.Path]::GetFullPath($internalSecretReference) } else { [IO.Path]::GetFullPath((Join-Path $runtimeDirectory $internalSecretReference)) }
    if (-not $internalSecretPath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "InternalServiceSecretReference 必须位于 RuntimeDirectory 内：$internalSecretPath" }
    $config.InternalServiceSecretReference = $internalSecretPath
    $tlsCertificateReference = [string]$config.CustomerWebTlsCertificateReference
    $tlsKeyReference = [string]$config.CustomerWebTlsKeyReference
    if ([string]::IsNullOrWhiteSpace($tlsCertificateReference) -xor [string]::IsNullOrWhiteSpace($tlsKeyReference)) {
        throw 'Customer Web TLS certificate 与 key 必须同时配置或同时留空。'
    }
    foreach ($tlsKey in @('CustomerWebTlsCertificateReference','CustomerWebTlsKeyReference')) {
        $tlsReference = [string]$config[$tlsKey]
        if ([string]::IsNullOrWhiteSpace($tlsReference)) { continue }
        $tlsPath = if ([IO.Path]::IsPathRooted($tlsReference)) { [IO.Path]::GetFullPath($tlsReference) } else { [IO.Path]::GetFullPath((Join-Path $runtimeDirectory $tlsReference)) }
        if (-not $tlsPath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "$tlsKey 必须位于 RuntimeDirectory 内：$tlsPath" }
        $config[$tlsKey] = $tlsPath
    }
    $channelAgentTimeout = 0
    if (-not [int]::TryParse([string]$config.ChannelAgentTimeoutSeconds, [ref]$channelAgentTimeout) -or $channelAgentTimeout -lt 1 -or $channelAgentTimeout -gt 60) {
        throw 'ChannelAgentTimeoutSeconds 必须为 1-60 的整数。'
    }
    $config.ChannelAgentTimeoutSeconds = $channelAgentTimeout
    if ([bool]$config.ChannelAgentIntegrationEnabled) {
        if ([string]::IsNullOrWhiteSpace([string]$config.ChannelAgentServerUrl)) {
            throw 'ChannelAgentIntegrationEnabled=true 时必须配置 ChannelAgentServerUrl。'
        }
        try {
            $channelAgentUri = [uri]$config.ChannelAgentServerUrl
            if (-not $channelAgentUri.IsAbsoluteUri -or $channelAgentUri.Scheme -notin @('http','https') -or [string]::IsNullOrWhiteSpace($channelAgentUri.Host) -or $channelAgentUri.UserInfo -or $channelAgentUri.AbsolutePath -ne '/') { throw 'invalid' }
            if ($channelAgentUri.Scheme -eq 'http' -and $channelAgentUri.Host -notin @('127.0.0.1','localhost','::1')) { throw 'remote-http' }
            $config.ChannelAgentServerUrl = $channelAgentUri.AbsoluteUri.TrimEnd('/')
        } catch {
            throw 'ChannelAgentServerUrl 必须是回环 HTTP 或 HTTPS 根地址；禁止用户信息、子路径和远程明文 HTTP。'
        }
        if ([string]::IsNullOrWhiteSpace([string]$config.ChannelAgentOperatorSessionReference)) {
            throw '启用 Channel Agent 时必须配置外部会话引用文件；禁止在配置中填写会话值。'
        }
        $agentReference = [string]$config.ChannelAgentOperatorSessionReference
        $agentReferencePath = if ([IO.Path]::IsPathRooted($agentReference)) { [IO.Path]::GetFullPath($agentReference) } else { [IO.Path]::GetFullPath((Join-Path $runtimeDirectory $agentReference)) }
        if (-not $agentReferencePath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'ChannelAgentOperatorSessionReference 必须位于 RuntimeDirectory 内。' }
        if (-not (Test-Path -LiteralPath $agentReferencePath -PathType Leaf)) { throw "ChannelAgentOperatorSessionReference 不存在：$agentReferencePath" }
        $config.ChannelAgentOperatorSessionReference = $agentReferencePath
    }
    return $config
}

function Get-ServiceRecordPath($Config, [string]$Name) { Join-Path $Config.RuntimeDirectory "$Name.json" }
function Get-ServiceLogDirectory($Config) { Join-Path $Config.RuntimeDirectory 'logs' }
function Get-ConfiguredRuntimeMode($Config) {
    if ($Config.ContainsKey('RuntimeMode') -and -not [string]::IsNullOrWhiteSpace([string]$Config.RuntimeMode)) {
        return ([string]$Config.RuntimeMode).Trim().ToLowerInvariant()
    }
    return 'standard'
}
function Get-ConfiguredNetworkMode($Config) {
    if ($Config.ContainsKey('LanMode') -and [bool]$Config.LanMode) { return 'LAN' }
    return 'LOCAL'
}

function Get-RecordedRuntimeNetworkMode($Config) {
    $modes = @()
    $repositoryRoot = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
    foreach ($name in @('platform','rag','customer-web','admin-web')) {
        $recordPath = Get-ServiceRecordPath $Config $name
        if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) { continue }
        try {
            $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            throw "无法解析 $name 运行记录，拒绝自动选择 LOCAL/LAN：$recordPath"
        }
        if (-not ($record.PSObject.Properties.Name -contains 'repository_root') -or [string]::IsNullOrWhiteSpace([string]$record.repository_root)) {
            throw "$name 运行记录缺少 repository_root，拒绝自动选择 LOCAL/LAN。"
        }
        $recordRoot = [IO.Path]::GetFullPath([string]$record.repository_root)
        if (-not [string]::Equals($recordRoot, $repositoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "$name 运行记录指向其他仓库，拒绝自动选择 LOCAL/LAN：$recordRoot"
        }
        if (-not ($record.PSObject.Properties.Name -contains 'network_mode')) { continue }
        $networkMode = ([string]$record.network_mode).Trim().ToUpperInvariant()
        if ($networkMode -notin @('LOCAL','LAN')) {
            throw "$name 运行记录包含非法 network_mode：$networkMode"
        }
        $modes += $networkMode
    }
    $uniqueModes = @($modes | Select-Object -Unique)
    if ($uniqueModes.Count -gt 1) {
        throw "受管运行记录的 network_mode 不一致：$($uniqueModes -join '、')。请先使用状态脚本核对，禁止混合启动。"
    }
    if ($uniqueModes.Count -eq 1) { return [string]$uniqueModes[0] }
    return Get-StandardRuntimeNetworkModePreference $Config
}

function Get-StandardRuntimeNetworkModePreferencePath($Config) {
    return Join-Path ([string]$Config.RuntimeDirectory) 'network-mode.preference.json'
}

function Get-StandardRuntimeNetworkModePreference($Config) {
    $preferencePath = Get-StandardRuntimeNetworkModePreferencePath $Config
    if (-not (Test-Path -LiteralPath $preferencePath -PathType Leaf)) { return $null }
    try {
        $preference = Get-Content -LiteralPath $preferencePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "无法解析 Runtime 网络模式偏好，拒绝自动选择 LOCAL/LAN：$preferencePath"
    }
    foreach ($field in @('schema','repository_root','network_mode')) {
        if (-not ($preference.PSObject.Properties.Name -contains $field) -or [string]::IsNullOrWhiteSpace([string]$preference.$field)) {
            throw "Runtime 网络模式偏好缺少 $field：$preferencePath"
        }
    }
    if ([string]$preference.schema -ne 'ai-cs-runtime-network-mode.v1') { throw "未知 Runtime 网络模式偏好版本：$($preference.schema)" }
    $repositoryRoot = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
    $preferenceRoot = [IO.Path]::GetFullPath([string]$preference.repository_root)
    if (-not [string]::Equals($preferenceRoot, $repositoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime 网络模式偏好指向其他仓库，拒绝自动选择：$preferenceRoot"
    }
    $networkMode = ([string]$preference.network_mode).Trim().ToUpperInvariant()
    if ($networkMode -notin @('LOCAL','LAN')) { throw "Runtime 网络模式偏好非法：$networkMode" }
    return $networkMode
}

function Save-StandardRuntimeNetworkModePreference($Config, [string]$NetworkMode) {
    $normalizedMode = $NetworkMode.Trim().ToUpperInvariant()
    if ($normalizedMode -notin @('LOCAL','LAN')) { throw "不能保存非法 Runtime 网络模式：$NetworkMode" }
    New-Item -ItemType Directory -Force -Path ([string]$Config.RuntimeDirectory) | Out-Null
    [ordered]@{
        schema = 'ai-cs-runtime-network-mode.v1'
        repository_root = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
        network_mode = $normalizedMode
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath (Get-StandardRuntimeNetworkModePreferencePath $Config) -Encoding UTF8
}

function Resolve-StandardRuntimeNetworkMode($Config, [string]$Mode = 'Auto') {
    $requestedMode = if ([string]::IsNullOrWhiteSpace($Mode)) { 'AUTO' } else { $Mode.Trim().ToUpperInvariant() }
    if ($requestedMode -notin @('AUTO','LOCAL','LAN')) { throw 'Mode 只允许 Auto、Local 或 Lan。' }
    if ($requestedMode -ne 'AUTO') { return $requestedMode }
    $recordedMode = Get-RecordedRuntimeNetworkMode $Config
    if (-not [string]::IsNullOrWhiteSpace([string]$recordedMode)) { return $recordedMode }
    return Get-ConfiguredNetworkMode $Config
}
function Get-ServiceUrl($Config, [int]$Port, [string]$Path = '/') {
    $serviceHost = [string]$Config.BindAddress
    if ($serviceHost -in @('0.0.0.0', '::')) { $serviceHost = '127.0.0.1' }
    "http://${serviceHost}:$Port$Path"
}

function Get-AiCsGatewayContractVersion { return '1.0' }

function Get-AiCsGatewaySecretBytes($Config) {
    if (-not [bool]$Config.GatewayEnabled) { throw 'Gateway 未启用。' }
    $secretPath = [string]$Config.GatewaySecretReference
    if ([string]::IsNullOrWhiteSpace($secretPath) -or -not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
        throw 'Gateway secret reference 不可用。'
    }
    try {
        $secretText = [IO.File]::ReadAllText($secretPath, [Text.UTF8Encoding]::new($false, $true))
    } catch {
        throw 'Gateway secret reference 必须是可读取的 UTF-8 单行文件。'
    }
    $secretText = $secretText.TrimEnd(@([char]13, [char]10))
    if ($secretText.Contains("`r") -or $secretText.Contains("`n")) {
        throw 'Gateway secret reference 必须只包含一行。'
    }
    $secretBytes = [Text.Encoding]::UTF8.GetBytes($secretText)
    if ($secretBytes.Length -lt 32) { throw 'Gateway HMAC secret 至少需要 32 bytes。' }
    return $secretBytes
}

function Get-AiCsInternalServiceToken($Config) {
    $secretPath = [string]$Config.InternalServiceSecretReference
    if ([string]::IsNullOrWhiteSpace($secretPath) -or -not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
        throw 'Internal Service secret reference 不可用。'
    }
    $token = [IO.File]::ReadAllText($secretPath, [Text.Encoding]::UTF8).TrimEnd("`r", "`n")
    if ($token -match "[`r`n]" -or $token -match '[^\x20-\x7E]') { throw 'Internal Service secret 必须是单行 ASCII。' }
    if ([Text.Encoding]::ASCII.GetByteCount($token) -lt 32) { throw 'Internal Service secret 至少需要 32 bytes。' }
    return $token
}

function Get-AiCsInternalServiceHeaders($Config) {
    return @{ 'X-AI-CS-Service-Token' = Get-AiCsInternalServiceToken $Config }
}

function ConvertTo-AiCsBase64Url([byte[]]$Bytes) {
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-AiCsGatewayAuthHeaders(
    $Config,
    [ValidateSet('GET','POST')][string]$Method,
    [string]$Path,
    [byte[]]$Body = [byte[]]@(),
    [string]$Timestamp = '',
    [string]$Nonce = '',
    [string]$RequestId = '',
    [string]$CorrelationId = '',
    [string]$IdempotencyKey = ''
) {
    $contractVersion = Get-AiCsGatewayContractVersion
    if ([string]::IsNullOrWhiteSpace($RequestId)) { $RequestId = "runtime-$([Guid]::NewGuid().ToString('N'))" }
    if ([string]::IsNullOrWhiteSpace($CorrelationId)) { $CorrelationId = "runtime-$([Guid]::NewGuid().ToString('N'))" }
    if ([string]::IsNullOrWhiteSpace($IdempotencyKey)) { $IdempotencyKey = "runtime-$([Guid]::NewGuid().ToString('N'))" }
    if ([string]::IsNullOrWhiteSpace($Nonce)) { $Nonce = [Guid]::NewGuid().ToString('N') }
    if ([string]::IsNullOrWhiteSpace($Timestamp)) { $Timestamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ', [Globalization.CultureInfo]::InvariantCulture) }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $contentHash = ([BitConverter]::ToString($sha.ComputeHash($Body))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
    $signingText = @(
        'HMAC-SHA256',
        $Method.ToUpperInvariant(),
        $Path,
        $contractVersion,
        [string]$Config.GatewayClientId,
        [string]$Config.GatewayKeyId,
        $Timestamp,
        $Nonce,
        $RequestId,
        $CorrelationId,
        $IdempotencyKey,
        $contentHash
    ) -join "`n"
    $hmac = [Security.Cryptography.HMACSHA256]::new((Get-AiCsGatewaySecretBytes $Config))
    try { $signature = ConvertTo-AiCsBase64Url ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($signingText))) } finally { $hmac.Dispose() }
    return @{
        Authorization = "HMAC-SHA256 Credential=$($Config.GatewayClientId)/$($Config.GatewayKeyId),Signature=$signature"
        'X-AI-CS-Contract-Version' = $contractVersion
        'X-AI-CS-Timestamp' = $Timestamp
        'X-AI-CS-Nonce' = $Nonce
        'X-AI-CS-Content-SHA256' = $contentHash
        'X-Request-ID' = $RequestId
        'X-Correlation-ID' = $CorrelationId
        'Idempotency-Key' = $IdempotencyKey
    }
}

function Assert-AiCsGatewayProductionConfig($Config) {
    if (-not [bool]$Config.GatewayEnabled) { throw 'Production Server Runtime 要求 GatewayEnabled=true。' }
    if ((Get-ConfiguredRuntimeMode $Config) -notin @('standard','shadow','recovery')) {
        throw 'Production Server Runtime 只允许 standard、shadow 或 recovery。'
    }
    Get-AiCsGatewaySecretBytes $Config | Out-Null
    if ([string]$Config.BindAddress -notin @('127.0.0.1','localhost')) {
        throw 'Production Server Runtime 要求 A Core BindAddress 保持回环；LAN Gateway 必须使用独立受控入口。'
    }
    $repositoryRoot = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
    $secretPath = [IO.Path]::GetFullPath([string]$Config.GatewaySecretReference)
    $repositoryPrefix = $repositoryRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ($secretPath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        # Windows PowerShell 5.1 runs on .NET Framework, where
        # System.IO.Path.GetRelativePath is unavailable. The prefix check above
        # already proves that this path is a descendant of RepositoryRoot.
        $relativeSecretPath = $secretPath.Substring($repositoryPrefix.Length).Replace('\', '/')
        $tracked = @(& git -C $repositoryRoot ls-files -- $relativeSecretPath 2>$null)
        if ($LASTEXITCODE -ne 0) { throw '无法验证 Gateway secret reference 的 Git 状态。' }
        if ($tracked.Count -gt 0) { throw 'Gateway secret reference 指向 Git 已跟踪文件；Production Runtime 拒绝启动。' }
    }
    return $true
}

function Get-AiCsGatewayRuntimeHealth($Config) {
    Assert-AiCsGatewayProductionConfig $Config | Out-Null
    $path = '/gateway/v1/health'
    $headers = New-AiCsGatewayAuthHeaders $Config 'GET' $path
    $origin = if ($Config.ContainsKey('GatewayEndpointOrigin') -and -not [string]::IsNullOrWhiteSpace([string]$Config.GatewayEndpointOrigin)) { [string]$Config.GatewayEndpointOrigin } else { Get-ServiceUrl $Config ([int]$Config.RagPort) '' }
    $health = Invoke-RestMethod -UseBasicParsing -Method Get -Uri "$($origin.TrimEnd('/'))$path" -Headers $headers -TimeoutSec 5
    if ([string]$health.contract_version -ne (Get-AiCsGatewayContractVersion)) { throw 'Gateway health contract_version 不匹配。' }
    if ([string]::IsNullOrWhiteSpace([string]$health.version)) { throw 'Gateway health 缺少 version。' }
    if ([string]$health.status -notin @('HEALTHY','UNHEALTHY')) { throw "Gateway health 状态无效：$($health.status)" }
    return $health
}

function Wait-AiCsGatewayRuntimeReady($Config, [int]$Seconds = 120) {
    $lastState = 'UNREACHABLE'
    for ($attempt = 0; $attempt -lt $Seconds; $attempt++) {
        try {
            $health = Get-AiCsGatewayRuntimeHealth $Config
            $lastState = [string]$health.status
            if ($lastState -eq 'HEALTHY') { return $health }
        } catch {
            $lastState = 'UNREACHABLE'
        }
        Start-Sleep -Seconds 1
    }
    throw "Gateway 未在 $Seconds 秒内达到 HEALTHY；最后状态=$lastState。"
}

function Get-AiCsServerRuntimeConsole($Config) {
    return Get-Json (Get-ServiceUrl $Config ([int]$Config.RagPort) '/api/admin/server-runtime') 'Server Runtime Console' (Get-AiCsInternalServiceHeaders $Config)
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

function ConvertTo-Ipv4UInt64([string]$Address) {
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed) -or $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw "无效 IPv4 地址：$Address"
    }
    $bytes = $parsed.GetAddressBytes()
    return [uint64](([uint64]$bytes[0] * 16777216) + ([uint64]$bytes[1] * 65536) + ([uint64]$bytes[2] * 256) + [uint64]$bytes[3])
}

function Get-Ipv4CidrRange([string]$Cidr) {
    $parts = $Cidr.Split('/')
    $prefix = 0
    if ($parts.Count -ne 2 -or -not [int]::TryParse($parts[1], [ref]$prefix) -or $prefix -lt 1 -or $prefix -gt 30) {
        throw "无效 IPv4 CIDR：$Cidr"
    }
    $addressValue = ConvertTo-Ipv4UInt64 $parts[0]
    $hostCount = [uint64][Math]::Pow(2, 32 - $prefix)
    $mask = [uint64](4294967296 - $hostCount)
    $networkValue = [uint64]($addressValue -band $mask)
    if ($addressValue -ne $networkValue) { throw "CIDR 必须使用规范网络地址：$Cidr" }
    return [pscustomobject]@{ Network=$networkValue; Broadcast=([uint64]($networkValue + $hostCount - 1)); PrefixLength=$prefix }
}

function Test-PrivateLanCidr([string]$Cidr) {
    try {
        $range = Get-Ipv4CidrRange $Cidr
        $address = $Cidr.Split('/')[0]
        if (-not (Test-PrivateLanIpv4 $address)) { return $false }
        $privateRanges = @(
            Get-Ipv4CidrRange '10.0.0.0/8'
            Get-Ipv4CidrRange '172.16.0.0/12'
            Get-Ipv4CidrRange '192.168.0.0/16'
        )
        return @($privateRanges | Where-Object { $range.Network -ge $_.Network -and $range.Broadcast -le $_.Broadcast }).Count -eq 1
    } catch { return $false }
}

function Test-Ipv4InCidr([string]$Address, [string]$Cidr) {
    try {
        $value = ConvertTo-Ipv4UInt64 $Address
        $range = Get-Ipv4CidrRange $Cidr
        return $value -ge $range.Network -and $value -le $range.Broadcast
    } catch { return $false }
}

function Test-Ipv4CidrWithin([string]$CandidateCidr, [string]$ParentCidr) {
    try {
        $candidate = Get-Ipv4CidrRange $CandidateCidr
        $parent = Get-Ipv4CidrRange $ParentCidr
        return $candidate.Network -ge $parent.Network -and $candidate.Broadcast -le $parent.Broadcast
    } catch { return $false }
}

function Test-LanAdapterEligible($Adapter) {
    if ([string]$Adapter.Status -ne 'Up') { return $false }
    $description = "{0} {1}" -f [string]$Adapter.Name, [string]$Adapter.InterfaceDescription
    if ($description -match '(?i)(virtual|vmware|hyper-v|vethernet|wsl|docker|loopback|bluetooth|tunnel|tap|tun|vpn|wireguard|tailscale|zerotier)') { return $false }
    if ($Adapter.PSObject.Properties.Match('HardwareInterface').Count -gt 0 -and $null -ne $Adapter.HardwareInterface -and -not [bool]$Adapter.HardwareInterface) { return $false }
    return $true
}

function Get-LanAdapterKind($Candidate) {
    $description = "{0} {1}" -f [string]$Candidate.InterfaceAlias, [string]$Candidate.InterfaceDescription
    if ($description -match '(?i)(ethernet|以太网)') { return 'Ethernet' }
    if ($description -match '(?i)(wi-?fi|wlan|wireless|无线)') { return 'WLAN' }
    return 'Other'
}

function Get-Ipv4SubnetMask([int]$PrefixLength) {
    if ($PrefixLength -lt 0 -or $PrefixLength -gt 32) { throw "无效的 IPv4 前缀长度：$PrefixLength" }
    $mask = [byte[]]@(0, 0, 0, 0)
    $remaining = $PrefixLength
    for ($index = 0; $index -lt 4; $index++) {
        $bits = [Math]::Min(8, $remaining)
        $mask[$index] = if ($bits -eq 0) { 0 } else { [byte](256 - [Math]::Pow(2, 8 - $bits)) }
        $remaining -= $bits
    }
    return ($mask -join '.')
}

function Get-LanSubnetCidr($Candidate) {
    $prefixLength = [int]$Candidate.PrefixLength
    if ($prefixLength -lt 1 -or $prefixLength -gt 30) { throw "局域网 IPv4 前缀长度必须在 1-30 之间：$prefixLength" }
    $address = [System.Net.IPAddress]::Parse([string]$Candidate.IPAddress).GetAddressBytes()
    $mask = (Get-Ipv4SubnetMask $prefixLength).Split('.') | ForEach-Object { [byte]$_ }
    $network = for ($index = 0; $index -lt 4; $index++) { [byte]($address[$index] -band $mask[$index]) }
    return "$($network -join '.')/$prefixLength"
}

function Get-Ipv4PrefixLengthFromMask([System.Net.IPAddress]$Mask) {
    if ($null -eq $Mask) { return 0 }
    $prefixLength = 0
    foreach ($byte in $Mask.GetAddressBytes()) {
        for ($bit = 7; $bit -ge 0; $bit--) {
            if (($byte -band (1 -shl $bit)) -ne 0) { $prefixLength++ }
        }
    }
    return $prefixLength
}

function Get-LanVpnRiskAdapters {
    try {
        return @([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {
            ("$($_.Name) $($_.Description)") -match '(?i)(vpn|tun|tap|wireguard|tailscale|zerotier)'
        } | ForEach-Object {
            [pscustomobject]@{ Name=[string]$_.Name; InterfaceDescription=[string]$_.Description }
        })
    } catch {
        return @()
    }
}

function Get-LanIpv4Candidates([switch]$UseLegacyPowerShellDiscovery) {
    $candidates = @()
    if (-not $UseLegacyPowerShellDiscovery) {
        try {
            $interfaces = @([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces())
        } catch {
            throw "无法通过.NET读取Windows网络适配器：$($_.Exception.Message)"
        }
        foreach ($networkInterface in $interfaces) {
            if ($networkInterface.OperationalStatus -ne [System.Net.NetworkInformation.OperationalStatus]::Up) { continue }
            $adapter = [pscustomobject]@{
                Status = 'Up'
                Name = [string]$networkInterface.Name
                InterfaceDescription = [string]$networkInterface.Description
                HardwareInterface = $networkInterface.NetworkInterfaceType -in @(
                    [System.Net.NetworkInformation.NetworkInterfaceType]::Ethernet,
                    [System.Net.NetworkInformation.NetworkInterfaceType]::GigabitEthernet,
                    [System.Net.NetworkInformation.NetworkInterfaceType]::Wireless80211
                )
            }
            if (-not (Test-LanAdapterEligible $adapter)) { continue }
            try {
                $properties = $networkInterface.GetIPProperties()
                $ipv4Properties = $properties.GetIPv4Properties()
            } catch { continue }
            if ($null -eq $ipv4Properties) { continue }
            $gateways = @($properties.GatewayAddresses | Where-Object {
                $null -ne $_.Address -and
                $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                -not [string]::IsNullOrWhiteSpace([string]$_.Address)
            })
            if ($gateways.Count -eq 0) { continue }
            foreach ($unicast in @($properties.UnicastAddresses)) {
                if ($unicast.Address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { continue }
                $ip = [string]$unicast.Address
                if (-not (Test-PrivateLanIpv4 $ip)) { continue }
                $prefixLength = 0
                if ($unicast.PSObject.Properties.Name -contains 'PrefixLength') {
                    $prefixLength = [int]$unicast.PrefixLength
                }
                if ($prefixLength -lt 1 -or $prefixLength -gt 30) {
                    $prefixLength = Get-Ipv4PrefixLengthFromMask $unicast.IPv4Mask
                }
                if ($prefixLength -lt 1 -or $prefixLength -gt 30) { continue }
                $candidates += [pscustomobject]@{
                    IPAddress = $ip
                    InterfaceIndex = [int]$ipv4Properties.Index
                    InterfaceAlias = [string]$networkInterface.Name
                    InterfaceDescription = [string]$networkInterface.Description
                    PrefixLength = $prefixLength
                    SubnetMask = Get-Ipv4SubnetMask $prefixLength
                    DefaultGateway = [string]$gateways[0].Address
                }
            }
        }
        return @($candidates | Sort-Object InterfaceIndex, IPAddress -Unique)
    }

    # Kept only as a deterministic unit-test seam and compatibility diagnostic.
    # Production start/status paths use the bounded .NET enumeration above.
    try {
        $adapters = @(Get-NetAdapter -ErrorAction Stop)
    } catch {
        throw "无法读取 Windows 网络适配器：$($_.Exception.Message)"
    }
    foreach ($adapter in $adapters) {
        if (-not (Test-LanAdapterEligible $adapter)) { continue }
        $interfaceIndex = [int]$adapter.ifIndex
        $networkConfiguration = Get-NetIPConfiguration -InterfaceIndex $interfaceIndex -ErrorAction SilentlyContinue
        [array]$gateways = if ($null -eq $networkConfiguration) { @() } else { @($networkConfiguration.IPv4DefaultGateway | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.NextHop) }) }
        if ($gateways.Count -eq 0) { continue }
        $gateway = [string]$gateways[0].NextHop
        $addresses = @(Get-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
        foreach ($address in $addresses) {
            $ip = [string]$address.IPAddress
            if (-not (Test-PrivateLanIpv4 $ip)) { continue }
            $candidates += [pscustomobject]@{
                IPAddress = $ip
                InterfaceIndex = $interfaceIndex
                InterfaceAlias = [string]$adapter.Name
                InterfaceDescription = [string]$adapter.InterfaceDescription
                PrefixLength = [int]$address.PrefixLength
                SubnetMask = Get-Ipv4SubnetMask ([int]$address.PrefixLength)
                DefaultGateway = $gateway
            }
        }
    }
    return @($candidates | Sort-Object InterfaceIndex, IPAddress -Unique)
}

function Get-LanNetworkProfile($Candidate) {
    $job = $null
    try {
        $job = Start-Job -ScriptBlock {
            param([int]$InterfaceIndex)
            @(Get-NetConnectionProfile -InterfaceIndex $InterfaceIndex -ErrorAction Stop) |
                Select-Object -First 1 -Property Name, NetworkCategory
        } -ArgumentList ([int]$Candidate.InterfaceIndex)
        if ($null -eq (Wait-Job -Job $job -Timeout 5)) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            return [pscustomobject]@{
                InterfaceAlias=[string]$Candidate.InterfaceAlias
                NetworkName=''
                NetworkCategory='Unknown'
                Detail='Windows网络类型查询超过5秒；已跳过，脚本未修改网络或防火墙。'
            }
        }
        $profiles = @(Receive-Job -Job $job -ErrorAction Stop)
    } catch {
        return [pscustomobject]@{ InterfaceAlias=[string]$Candidate.InterfaceAlias; NetworkName=''; NetworkCategory='Unknown'; Detail=$_.Exception.Message }
    } finally {
        if ($null -ne $job) { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
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
    $customerScheme = if ([string]::IsNullOrWhiteSpace([string]$Config.CustomerWebTlsCertificateReference)) { 'http' } else { 'https' }
    $lanOrigin = "${customerScheme}://$($Config.LanAdvertisedHost):$($Config.CustomerWebPort)"
    $origins = @(
        $lanOrigin,
        "${customerScheme}://127.0.0.1:$($Config.CustomerWebPort)",
        "${customerScheme}://localhost:$($Config.CustomerWebPort)",
        "http://127.0.0.1:$($Config.AdminWebPort)",
        "http://localhost:$($Config.AdminWebPort)"
    ) | Select-Object -Unique
    if (@($origins | Where-Object { $_ -eq '*' -or $_ -match '\*' }).Count -gt 0) { throw '局域网 CORS 只允许显式 Origin，禁止通配符。' }
    return ($origins -join ',')
}

function Select-LanIpv4Candidate([object[]]$Candidates, [string]$LanAddress, [string]$PreferredInterfaceAlias) {
    $usable = @($Candidates | Where-Object {
        (Test-PrivateLanIpv4 ([string]$_.IPAddress)) -and
        -not [string]::IsNullOrWhiteSpace([string]$_.DefaultGateway) -and
        [int]$_.PrefixLength -ge 1 -and [int]$_.PrefixLength -le 30
    })
    if ($usable.Count -eq 0) {
        throw '未发现状态为 Up、具有私有 IPv4 和默认网关的物理网卡。请连接公司网络后重试。'
    }

    $requestedAddress = if ([string]::IsNullOrWhiteSpace($LanAddress)) { 'auto' } else { $LanAddress.Trim() }
    if ($requestedAddress -ne 'auto') {
        if (-not (Test-PrivateLanIpv4 $requestedAddress)) { throw "LanAddress 必须为 auto 或有效的私有 IPv4；拒绝地址：$requestedAddress" }
        $match = @($usable | Where-Object { [string]$_.IPAddress -eq $requestedAddress })
        if ($match.Count -ne 1) { throw "LanAddress=$requestedAddress 不属于当前有默认网关的有效物理网卡。请改为 auto 或检查网卡。" }
        return $match[0]
    }

    if (-not [string]::IsNullOrWhiteSpace($PreferredInterfaceAlias)) {
        $preferred = @($usable | Where-Object { [string]$_.InterfaceAlias -ieq $PreferredInterfaceAlias.Trim() })
        if ($preferred.Count -ne 1) {
            $available = @($usable | ForEach-Object { "$($_.InterfaceAlias)（$($_.IPAddress)）" }) -join '；'
            throw "PreferredInterfaceAlias=$PreferredInterfaceAlias 未唯一匹配有效网卡。可用项：$available"
        }
        return $preferred[0]
    }

    $ranked = @($usable | ForEach-Object {
        [pscustomobject]@{ Candidate = $_; Rank = switch (Get-LanAdapterKind $_) { 'Ethernet' { 0 }; 'WLAN' { 1 }; default { 2 } } }
    })
    $bestRank = ($ranked | Measure-Object -Property Rank -Minimum).Minimum
    $best = @($ranked | Where-Object { $_.Rank -eq $bestRank } | ForEach-Object { $_.Candidate })
    if ($best.Count -ne 1) {
        $available = @($best | ForEach-Object { "$($_.IPAddress)（$($_.InterfaceAlias)）" }) -join '；'
        throw "发现同优先级的多个有效物理网卡：$available。为避免选择错误网段，请在 config.local.ps1 设置 PreferredInterfaceAlias。"
    }
    return $best[0]
}

function Resolve-LanRuntimeConfig($Config, [object[]]$Candidates, $NetworkProfile, [switch]$SkipPublicNetworkGuard) {
    if (
        [string]::IsNullOrWhiteSpace([string]$Config.CustomerWebTlsCertificateReference) -or
        [string]::IsNullOrWhiteSpace([string]$Config.CustomerWebTlsKeyReference)
    ) {
        throw 'LAN Runtime 必须配置 Customer Web TLS certificate/key 文件引用；禁止通过明文 HTTP 暴露登录与 Bearer。'
    }
    if ($null -eq $Candidates) { $Candidates = @(Get-LanIpv4Candidates) }
    $selected = Select-LanIpv4Candidate $Candidates ([string]$Config.LanAddress) ([string]$Config.PreferredInterfaceAlias)
    if ($null -eq $NetworkProfile) { $NetworkProfile = Get-LanNetworkProfile $selected }
    if (-not $SkipPublicNetworkGuard) { Assert-LanNetworkSafety $Config $NetworkProfile }

    $lanConfig = @{}
    foreach ($entry in $Config.GetEnumerator()) { $lanConfig[$entry.Key] = $entry.Value }
    $lanConfig.EnableLanMode = $true
    $lanConfig.LanMode = $true
    $lanConfig.LanAddress = [string]$selected.IPAddress
    $lanConfig.LanAdvertisedHost = [string]$selected.IPAddress
    # Only the production TLS static server accepts the LAN connection. A and C
    # stay loopback-only and are reached through two fixed same-origin prefixes.
    $lanConfig.BindAddress = '127.0.0.1'
    $lanConfig.RagBindAddress = '127.0.0.1'
    $lanConfig.PlatformBindAddress = '127.0.0.1'
    $lanConfig.CustomerWebBindAddress = [string]$selected.IPAddress
    $lanConfig.CustomerWebUrl = "https://$($lanConfig.LanAdvertisedHost):$($lanConfig.CustomerWebPort)/"
    $lanConfig.LocalCustomerWebUrl = $lanConfig.CustomerWebUrl
    $lanConfig.LanNetworkProfile = $NetworkProfile
    $lanConfig.LanSelection = $selected
    $lanConfig.LanSubnet = Get-LanSubnetCidr $selected
    $lanConfig.LanCorsAllowedOrigins = Get-LanCorsAllowedOrigins $lanConfig
    return $lanConfig
}

function Resolve-AiCsGatewayNetworkConfig($Config, [ValidateSet('LOCAL','LAN')] [string]$NetworkMode, [object[]]$Candidates = $null, $NetworkProfile = $null) {
    $gatewayConfig = @{}
    foreach ($entry in $Config.GetEnumerator()) { $gatewayConfig[$entry.Key] = $entry.Value }
    if ($NetworkMode -eq 'LOCAL') {
        $gatewayConfig.LanMode = $false
        $gatewayConfig.EnableLanMode = $false
        $gatewayConfig.GatewayNetworkMode = 'LOCAL'
        $gatewayConfig.GatewayEndpointOrigin = "http://127.0.0.1:$($gatewayConfig.RagPort)"
        $gatewayConfig.GatewayLanBindAddressResolved = '127.0.0.1'
        $gatewayConfig.GatewayAllowedNetworksResolved = @()
        return $gatewayConfig
    }

    $lanConfig = Resolve-LanRuntimeConfig $Config $Candidates $NetworkProfile
    if ([string]$lanConfig.LanNetworkProfile.NetworkCategory -ne 'Private') {
        throw 'Gateway LAN 模式仅允许 Windows Private 网络；Unknown/Public 均拒绝启动，且不会修改网络配置。'
    }
    $selectedAddress = [string]$lanConfig.LanSelection.IPAddress
    $configuredBind = [string]$lanConfig.GatewayLanBindAddress
    if ($configuredBind -ne 'auto' -and $configuredBind -ne $selectedAddress) {
        throw "GatewayLanBindAddress=$configuredBind 与选定物理网卡地址 $selectedAddress 不一致。"
    }
    $allowedNetworks = if (@($lanConfig.GatewayAllowedNetworks) -contains 'auto') { @([string]$lanConfig.LanSubnet) } else { @($lanConfig.GatewayAllowedNetworks) }
    foreach ($network in $allowedNetworks) {
        if (-not (Test-PrivateLanCidr ([string]$network)) -or -not (Test-Ipv4CidrWithin ([string]$network) ([string]$lanConfig.LanSubnet))) {
            throw "Gateway allowed network 必须位于当前物理网卡子网 $($lanConfig.LanSubnet) 内：$network"
        }
    }
    $lanConfig.GatewayNetworkMode = 'LAN'
    $lanConfig.GatewayLanBindAddressResolved = $selectedAddress
    $lanConfig.GatewayAllowedNetworksResolved = @($allowedNetworks)
    $lanConfig.GatewayEndpointOrigin = "http://${selectedAddress}:$($lanConfig.GatewayLanPort)"
    $lanConfig.GatewayUpstreamOrigin = "http://127.0.0.1:$($lanConfig.RagPort)"
    return $lanConfig
}

function Resolve-LanStatusRuntimeConfig($Config) {
    $recordPath = Get-ServiceRecordPath $Config 'customer-web'
    if (Test-Path -LiteralPath $recordPath -PathType Leaf) {
        try {
            $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $recordRoot = [IO.Path]::GetFullPath([string]$record.repository_root)
            $expectedRoot = [IO.Path]::GetFullPath([string]$Config.RepositoryRoot)
            $healthUri = [uri][string]$record.healthUrl
            if (
                [string]$record.network_mode -eq 'LAN' -and
                [string]::Equals($recordRoot, $expectedRoot, [StringComparison]::OrdinalIgnoreCase) -and
                $healthUri.IsAbsoluteUri -and
                $healthUri.Scheme -in @('http','https') -and
                $healthUri.Port -eq [int]$Config.CustomerWebPort -and
                (Test-PrivateLanIpv4 $healthUri.Host)
            ) {
                $statusConfig = @{}
                foreach ($entry in $Config.GetEnumerator()) { $statusConfig[$entry.Key] = $entry.Value }
                $selection = [pscustomobject]@{
                    IPAddress = $healthUri.Host
                    InterfaceIndex = 0
                    InterfaceAlias = '受管运行记录'
                    InterfaceDescription = '受管运行记录（状态命令不重新扫描网卡）'
                    PrefixLength = 0
                    SubnetMask = '未探测'
                    DefaultGateway = '未探测'
                }
                $statusConfig.EnableLanMode = $true
                $statusConfig.LanMode = $true
                $statusConfig.LanAddress = $healthUri.Host
                $statusConfig.LanAdvertisedHost = $healthUri.Host
                $statusConfig.BindAddress = '127.0.0.1'
                $statusConfig.RagBindAddress = '127.0.0.1'
                $statusConfig.PlatformBindAddress = '127.0.0.1'
                $statusConfig.CustomerWebBindAddress = $healthUri.Host
                $statusConfig.CustomerWebUrl = $healthUri.AbsoluteUri
                $statusConfig.LocalCustomerWebUrl = $healthUri.AbsoluteUri
                $statusConfig.LanNetworkProfile = [pscustomobject]@{
                    InterfaceAlias = '受管运行记录'
                    NetworkName = '未重新探测'
                    NetworkCategory = 'Unknown'
                    Detail = '状态命令使用受管运行记录；动态网卡检查请运行诊断脚本。'
                }
                $statusConfig.LanSelection = $selection
                $statusConfig.LanSubnet = '未重新探测'
                $statusConfig.LanStatusResolutionSource = 'MANAGED_RECORD'
                return $statusConfig
            }
        } catch {
            # A malformed or stale record must not be trusted. The caller falls
            # back to the existing dynamic discovery and reports its failure.
        }
    }
    $dynamicConfig = Resolve-LanRuntimeConfig $Config $null $null -SkipPublicNetworkGuard
    $dynamicConfig.LanStatusResolutionSource = 'DYNAMIC_DISCOVERY'
    return $dynamicConfig
}

function Get-LanServiceListenerAddress($Config, [int]$Port) {
    $address = if ($Port -eq [int]$Config.RagPort) { [string]$Config.RagBindAddress } elseif ($Port -eq [int]$Config.PlatformPort) { [string]$Config.PlatformBindAddress } elseif ($Port -eq [int]$Config.CustomerWebPort) { [string]$Config.CustomerWebBindAddress } else { [string]$Config.BindAddress }
    return "${address}:$Port"
}

function Get-LanPlatformEnvironment($Config) {
    $integrationEnabled = if (-not [string]::IsNullOrWhiteSpace([string]$env:CHANNEL_AGENT_INTEGRATION_ENABLED)) { [string]$env:CHANNEL_AGENT_INTEGRATION_ENABLED } else { ([bool]$Config.ChannelAgentIntegrationEnabled).ToString().ToLowerInvariant() }
    $serverUrl = if (-not [string]::IsNullOrWhiteSpace([string]$env:CHANNEL_AGENT_SERVER_URL)) { [string]$env:CHANNEL_AGENT_SERVER_URL } else { [string]$Config.ChannelAgentServerUrl }
    return @{
        DATABASE_URL = [string]$Config.PlatformDatabaseUrl
        PLATFORM_DATABASE_BINDING_PATH = [string]$Config.PlatformDatabaseBindingPath
        PLATFORM_DATABASE_ENVIRONMENT_ID = [string]$Config.PlatformDatabaseEnvironmentId
        PLATFORM_REQUIRE_DATABASE_IDENTITY = ([bool]$Config.PlatformRequireDatabaseIdentity).ToString().ToLowerInvariant()
        CORS_ALLOWED_ORIGINS = [string]$Config.LanCorsAllowedOrigins
        PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR = [string]$Config.PlatformKnowledgeMaterialStorageDirectory
        AI_SERVICE_BASE_URL = "http://127.0.0.1:$($Config.RagPort)"
        CHANNEL_AGENT_INTEGRATION_ENABLED = $integrationEnabled
        CHANNEL_AGENT_SERVER_URL = $serverUrl
        CHANNEL_AGENT_OPERATOR_SESSION_FILE = [string]$Config.ChannelAgentOperatorSessionReference
        CHANNEL_AGENT_SERVICE_ID = [string]$env:CHANNEL_AGENT_SERVICE_ID
        CHANNEL_AGENT_SERVICE_KEY_ID = [string]$env:CHANNEL_AGENT_SERVICE_KEY_ID
        CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = [string]$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE
        CHANNEL_AGENT_CA_CERTIFICATE_FILE = [string]$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE
        CHANNEL_AGENT_TIMEOUT_SECONDS = [string]$Config.ChannelAgentTimeoutSeconds
        INTERNAL_SERVICE_SECRET_FILE = [string]$Config.InternalServiceSecretReference
    }
}

function Get-LocalPlatformEnvironment($Config) {
    $integrationEnabled = if (-not [string]::IsNullOrWhiteSpace([string]$env:CHANNEL_AGENT_INTEGRATION_ENABLED)) { [string]$env:CHANNEL_AGENT_INTEGRATION_ENABLED } else { ([bool]$Config.ChannelAgentIntegrationEnabled).ToString().ToLowerInvariant() }
    $serverUrl = if (-not [string]::IsNullOrWhiteSpace([string]$env:CHANNEL_AGENT_SERVER_URL)) { [string]$env:CHANNEL_AGENT_SERVER_URL } else { [string]$Config.ChannelAgentServerUrl }
    return @{
        DATABASE_URL = [string]$Config.PlatformDatabaseUrl
        PLATFORM_DATABASE_BINDING_PATH = [string]$Config.PlatformDatabaseBindingPath
        PLATFORM_DATABASE_ENVIRONMENT_ID = [string]$Config.PlatformDatabaseEnvironmentId
        PLATFORM_REQUIRE_DATABASE_IDENTITY = ([bool]$Config.PlatformRequireDatabaseIdentity).ToString().ToLowerInvariant()
        CORS_ALLOWED_ORIGINS = (@($Config.CorsAllowedOrigins) -join ',')
        PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR = [string]$Config.PlatformKnowledgeMaterialStorageDirectory
        AI_SERVICE_BASE_URL = "http://127.0.0.1:$($Config.RagPort)"
        CHANNEL_AGENT_INTEGRATION_ENABLED = $integrationEnabled
        CHANNEL_AGENT_SERVER_URL = $serverUrl
        CHANNEL_AGENT_OPERATOR_SESSION_FILE = [string]$Config.ChannelAgentOperatorSessionReference
        CHANNEL_AGENT_SERVICE_ID = [string]$env:CHANNEL_AGENT_SERVICE_ID
        CHANNEL_AGENT_SERVICE_KEY_ID = [string]$env:CHANNEL_AGENT_SERVICE_KEY_ID
        CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = [string]$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE
        CHANNEL_AGENT_CA_CERTIFICATE_FILE = [string]$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE
        CHANNEL_AGENT_TIMEOUT_SECONDS = [string]$Config.ChannelAgentTimeoutSeconds
        INTERNAL_SERVICE_SECRET_FILE = [string]$Config.InternalServiceSecretReference
    }
}

function Get-RagRuntimeEnvironment($Config, [string]$CorsAllowedOrigins) {
    $environment = @{
        CORS_ALLOWED_ORIGINS = $CorsAllowedOrigins
        LLM_PROVIDER = 'ollama'
        LLM_MODEL = [string]$Config.OllamaModel
        LLM_BASE_URL = [string]$Config.OllamaBaseUrl
        PLATFORM_API_BASE_URL = "http://127.0.0.1:$($Config.PlatformPort)"
        KNOWLEDGE_BASE_PATH = [string]$Config.RagKnowledgeBasePath
        VECTOR_DB_PATH = [string]$Config.RagVectorDbPath
        LOG_DIR = [string]$Config.RagLogDirectory
        CHROMA_COLLECTION_NAME = [string]$Config.RagPrimaryCollectionName
        TEST_KNOWLEDGE_COLLECTION_NAME = [string]$Config.RagActiveCollectionName
        ACTIVE_COLLECTION_NAME = [string]$Config.RagActiveCollectionName
        AI_CS_SERVER_RUNTIME_MODE = Get-ConfiguredRuntimeMode $Config
        AI_CS_SERVER_NETWORK_MODE = Get-ConfiguredNetworkMode $Config
        GATEWAY_ENABLED = ([bool]$Config.GatewayEnabled).ToString().ToLowerInvariant()
        GATEWAY_CLIENT_ID = [string]$Config.GatewayClientId
        GATEWAY_KEY_ID = [string]$Config.GatewayKeyId
        GATEWAY_STATE_PATH = [string]$Config.GatewayStatePath
        GATEWAY_CLOCK_SKEW_SECONDS = [string]$Config.GatewayClockSkewSeconds
        GATEWAY_NONCE_TTL_SECONDS = [string]$Config.GatewayNonceTtlSeconds
        GATEWAY_DECISION_RETENTION_SECONDS = [string]$Config.GatewayDecisionRetentionSeconds
        GATEWAY_DECISION_LEASE_SECONDS = [string]$Config.GatewayDecisionLeaseSeconds
        INTERNAL_SERVICE_SECRET_FILE = [string]$Config.InternalServiceSecretReference
    }
    if ([bool]$Config.GatewayEnabled) {
        $environment.GATEWAY_HMAC_SECRET_FILE = [string]$Config.GatewaySecretReference
    }
    return $environment
}

function Get-LanRagEnvironment($Config) { Get-RagRuntimeEnvironment $Config ([string]$Config.LanCorsAllowedOrigins) }

function Get-LocalRagEnvironment($Config) { Get-RagRuntimeEnvironment $Config ((@($Config.CorsAllowedOrigins) -join ',')) }

function Get-LanFrontendEnvironment($Config) {
    return @{
        VITE_RAG_API_BASE_URL = '/rag-api'
        VITE_PLATFORM_API_BASE_URL = '/platform-api'
        VITE_START_MODE = 'LAN'
        VITE_API_MODE = 'SAME_ORIGIN_PROXY'
        VITE_CUSTOMER_ENTRY_URL = [string]$Config.CustomerWebUrl
    }
}

function Get-LocalFrontendEnvironment($Config) {
    return @{
        VITE_RAG_API_BASE_URL = "http://127.0.0.1:$($Config.RagPort)"
        VITE_PLATFORM_API_BASE_URL = "http://127.0.0.1:$($Config.PlatformPort)"
        VITE_START_MODE = 'LOCAL'
        VITE_API_MODE = 'DIRECT'
        VITE_CUSTOMER_ENTRY_URL = [string]$Config.CustomerWebUrl
    }
}

function Get-AdminWebEnvironment($Config) {
    return @{
        VITE_PLATFORM_API_BASE_URL = "http://127.0.0.1:$($Config.PlatformPort)"
        VITE_AI_API_BASE_URL = "http://127.0.0.1:$($Config.RagPort)"
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
    $job = $null
    try {
        $job = Start-Job -ScriptBlock {
            param([string]$ProfileName)
            Get-NetFirewallProfile -Profile $ProfileName -ErrorAction Stop |
                Select-Object -First 1 -Property Name, Enabled
        } -ArgumentList $profileName
        if ($null -eq (Wait-Job -Job $job -Timeout 5)) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            return "Windows 防火墙状态：读取 $profileName 配置超过5秒；它仍可能阻断入站TCP 5173。脚本未修改任何规则。"
        }
        $profile = Receive-Job -Job $job -ErrorAction Stop
        if (-not [bool]$profile.Enabled) { return "Windows 防火墙状态：$profileName 配置文件已关闭（脚本未作任何修改）。" }
        return "Windows firewall: $profileName profile is enabled and may block inbound TCP 5173. A/C are loopback-only; do not open 8000 or 8011. Use the dedicated firewall tool only on a trusted network."
    } catch {
        return "Windows 防火墙状态：无法读取 $profileName 配置文件（$($_.Exception.Message)）；它仍可能阻断笔记本访问。脚本未修改任何规则。"
    } finally {
        if ($null -ne $job) { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
    }
}

function Get-AICustomerFirewallRuleName { return 'AI Customer Service LAN 5173 (Private)' }

function Get-AICustomerFirewallRules {
    return @(Get-NetFirewallRule -DisplayName (Get-AICustomerFirewallRuleName) -ErrorAction SilentlyContinue)
}

function Test-AiCsGatewayLanServiceRunning($Config) {
    $record = Test-RecordedProcess $Config 'gateway-lan'
    if (-not $record -or -not $record.Valid) { return $false }
    $runtimeIdentity = Test-ManagedServiceRuntimeIdentity $Config $record.Record
    if (-not $runtimeIdentity.Valid) { return $false }
    $listeners = @(Get-TcpListeningConnection ([int]$Config.GatewayLanPort))
    if ($listeners.Count -ne 1 -or [string]$listeners[0].LocalAddress -ne [string]$Config.GatewayLanBindAddressResolved) { return $false }
    try { return [string](Get-AiCsGatewayRuntimeHealth $Config).status -eq 'HEALTHY' } catch { return $false }
}

function Start-AiCsGatewayLanService($Config) {
    if ([string]$Config.GatewayNetworkMode -ne 'LAN') { throw 'Gateway LAN edge 只能在 LAN 模式启动。' }
    Assert-AiCsGatewayLanFirewallReady $Config | Out-Null
    if (Test-AiCsGatewayLanServiceRunning $Config) { return }
    Assert-PortAvailable $Config 'gateway-lan' ([int]$Config.GatewayLanPort)
    $arguments = @(
        '-m','app.gateway.lan_proxy',
        '--bind-address',[string]$Config.GatewayLanBindAddressResolved,
        '--port',[string]$Config.GatewayLanPort,
        '--interface-network',[string]$Config.LanSubnet,
        '--upstream-origin',[string]$Config.GatewayUpstreamOrigin,
        '--upstream-timeout-seconds',[string]$Config.GatewayUpstreamTimeoutSeconds
    )
    foreach ($network in @($Config.GatewayAllowedNetworksResolved)) { $arguments += @('--allowed-network',[string]$network) }
    Start-ManagedServiceWithEnvironment $Config 'gateway-lan' $Config.RagPythonPath $arguments (Join-Path $Config.RepositoryRoot 'backend') 'app.gateway.lan_proxy' ([int]$Config.GatewayLanPort) @{} | Out-Null
    try {
        Wait-AiCsGatewayRuntimeReady $Config 45 | Out-Null
        Update-ManagedServiceListenerRecord $Config 'gateway-lan' | Out-Null
    } catch {
        try { Stop-ManagedService $Config 'gateway-lan' } catch { Write-Warning "Gateway LAN startup cleanup failed: $($_.Exception.Message)" }
        throw
    }
}

function Get-AiCsGatewayLanServiceStatus($Config) {
    $probe = [pscustomobject]@{ Ok=$false; Error='signed Gateway health failed' }
    try {
        $health = Get-AiCsGatewayRuntimeHealth $Config
        $probe = [pscustomobject]@{ Ok=([string]$health.status -eq 'HEALTHY'); Error='' }
    } catch { }
    return Get-ServiceStatus $Config 'gateway-lan' ([int]$Config.GatewayLanPort) (Get-ManagedServiceHealthUrl $Config 'gateway-lan' ([int]$Config.GatewayLanPort)) $probe
}

function Get-AiCsGatewayFirewallRuleName($Config) { return "AI-CS Gateway LAN $($Config.GatewayLanPort) (Private)" }

function Get-AiCsGatewayFirewallRuleDetails($Config) {
    $rules = @(Get-NetFirewallRule -DisplayName (Get-AiCsGatewayFirewallRuleName $Config) -ErrorAction SilentlyContinue)
    return @($rules | ForEach-Object {
        $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $_ -ErrorAction Stop
        $addressFilter = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $_ -ErrorAction Stop
        [pscustomobject]@{
            Enabled = [string]$_.Enabled
            Direction = [string]$_.Direction
            Action = [string]$_.Action
            Profile = [string]$_.Profile
            Protocol = [string]$portFilter.Protocol
            LocalPort = @($portFilter.LocalPort)
            LocalAddress = @($addressFilter.LocalAddress)
            RemoteAddress = @($addressFilter.RemoteAddress)
        }
    })
}

function Test-StringSetEqual([object[]]$Actual, [object[]]$Expected) {
    $actualValues = @($Actual | ForEach-Object { ([string]$_).Trim() } | Sort-Object -Unique)
    $expectedValues = @($Expected | ForEach-Object { ([string]$_).Trim() } | Sort-Object -Unique)
    if ($actualValues.Count -ne $expectedValues.Count) { return $false }
    return (@(Compare-Object -ReferenceObject $expectedValues -DifferenceObject $actualValues -CaseSensitive).Count -eq 0)
}

function ConvertTo-CanonicalFirewallCidr([string]$Address) {
    $value = $Address.Trim()
    if ($value -match '^([^/]+)/([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$') {
        try {
            $prefix = Get-Ipv4PrefixLengthFromMask ([System.Net.IPAddress]::Parse($Matches[2]))
            return "$($Matches[1])/$prefix"
        } catch { return $value }
    }
    return $value
}

function Get-AiCsGatewayLanFirewallReadiness($Config, [scriptblock]$RuleProvider = $null) {
    $expectedName = Get-AiCsGatewayFirewallRuleName $Config
    $expectedNetworks = @($Config.GatewayAllowedNetworksResolved)
    $expectedAddress = [string]$Config.GatewayLanBindAddressResolved
    $rules = @(if ($RuleProvider) { & $RuleProvider } else { Get-AiCsGatewayFirewallRuleDetails $Config })
    if ($rules.Count -eq 0) {
        return [pscustomobject]@{ Ready=$false; State='MISSING'; RuleName=$expectedName; BindAddress=$expectedAddress; Port=[int]$Config.GatewayLanPort; AllowedNetworks=$expectedNetworks }
    }
    if ($rules.Count -ne 1) {
        return [pscustomobject]@{ Ready=$false; State='AMBIGUOUS'; RuleName=$expectedName; BindAddress=$expectedAddress; Port=[int]$Config.GatewayLanPort; AllowedNetworks=$expectedNetworks }
    }
    $rule = $rules[0]
    $protocolOk = [string]$rule.Protocol -in @('TCP','6')
    $portOk = Test-StringSetEqual @($rule.LocalPort) @([string]$Config.GatewayLanPort)
    $localAddressOk = Test-StringSetEqual @($rule.LocalAddress) @($expectedAddress)
    $normalizedRemoteAddresses = @($rule.RemoteAddress | ForEach-Object { ConvertTo-CanonicalFirewallCidr ([string]$_) })
    $remoteAddressOk = Test-StringSetEqual $normalizedRemoteAddresses $expectedNetworks
    $metadataOk = [string]$rule.Enabled -eq 'True' -and [string]$rule.Direction -eq 'Inbound' -and [string]$rule.Action -eq 'Allow' -and [string]$rule.Profile -eq 'Private'
    $ready = $metadataOk -and $protocolOk -and $portOk -and $localAddressOk -and $remoteAddressOk
    $state = if ($ready) { 'READY' } elseif (-not $metadataOk) { 'RULE_POLICY_MISMATCH' } elseif (-not $protocolOk -or -not $portOk) { 'RULE_PORT_MISMATCH' } elseif (-not $localAddressOk) { 'RULE_LOCAL_ADDRESS_MISMATCH' } else { 'RULE_REMOTE_NETWORK_MISMATCH' }
    return [pscustomobject]@{ Ready=$ready; State=$state; RuleName=$expectedName; BindAddress=$expectedAddress; Port=[int]$Config.GatewayLanPort; AllowedNetworks=$expectedNetworks }
}

function Assert-AiCsGatewayLanFirewallReady($Config, [scriptblock]$RuleProvider = $null) {
    $readiness = Get-AiCsGatewayLanFirewallReadiness $Config $RuleProvider
    if (-not $readiness.Ready) {
        throw "Gateway LAN 防火墙 Gate=$($readiness.State)。需要启用的 Private 入站规则：$($readiness.RuleName)，TCP $($readiness.BindAddress):$($readiness.Port)，Remote=$($readiness.AllowedNetworks -join ',')。脚本不会关闭或自动修改 Windows 防火墙；请先运行 check_ai_cs_gateway_firewall.ps1 并由管理员显式配置。"
    }
    return $readiness
}

function Test-AICustomerServiceAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ManagedServiceHealthUrl($Config, [string]$Name, [int]$FallbackPort = 0) {
    $bindAddress = if ($Config.ContainsKey('BindAddress')) { [string]$Config.BindAddress } else { '127.0.0.1' }
    if ($bindAddress -in @('0.0.0.0', '::', '')) { $bindAddress = '127.0.0.1' }
    if ($Name -eq 'customer-web') {
        if ($Config.ContainsKey('CustomerWebUrl') -and -not [string]::IsNullOrWhiteSpace([string]$Config.CustomerWebUrl)) { return [string]$Config.CustomerWebUrl }
        return "http://${bindAddress}:$FallbackPort/"
    }
    if ($Name -eq 'platform') {
        $port = if ($Config.ContainsKey('PlatformPort')) { [int]$Config.PlatformPort } else { $FallbackPort }
        $path = if ($Config.ContainsKey('PlatformHealthPath')) { [string]$Config.PlatformHealthPath } else { '/health' }
        return "http://${bindAddress}:$port$path"
    }
    if ($Name -eq 'rag') {
        $port = if ($Config.ContainsKey('RagPort')) { [int]$Config.RagPort } else { $FallbackPort }
        $path = if ($Config.ContainsKey('RagHealthPath')) { [string]$Config.RagHealthPath } else { '/api/health' }
        return "http://${bindAddress}:$port$path"
    }
    if ($Name -eq 'admin-web') {
        if ($Config.ContainsKey('AdminWebUrl') -and -not [string]::IsNullOrWhiteSpace([string]$Config.AdminWebUrl)) { return [string]$Config.AdminWebUrl }
        $port = if ($Config.ContainsKey('AdminWebPort')) { [int]$Config.AdminWebPort } else { $FallbackPort }
        $adminBindAddress = if ($Config.ContainsKey('AdminWebBindAddress')) { [string]$Config.AdminWebBindAddress } else { '127.0.0.1' }
        if ($adminBindAddress -in @('0.0.0.0', '::', '')) { $adminBindAddress = '127.0.0.1' }
        return "http://${adminBindAddress}:$port/"
    }
    if ($Name -eq 'gateway-lan') {
        $origin = if ($Config.ContainsKey('GatewayEndpointOrigin')) { [string]$Config.GatewayEndpointOrigin } else { "http://127.0.0.1:$FallbackPort" }
        return "$($origin.TrimEnd('/'))/gateway/v1/health"
    }
    # Test helpers may register a deliberately unknown service name to verify
    # that a tampered record cannot stop it. Its record still needs a harmless
    # loopback URL; normal launchers only use the three standard names above.
    return "http://${bindAddress}:$FallbackPort/"
}

function Get-ManagedServiceExpectedListenerAddress($Config, [string]$Name, [int]$Port) {
    if ($Name -eq 'gateway-lan') {
        $address = if ($Config.ContainsKey('GatewayLanBindAddressResolved')) { [string]$Config.GatewayLanBindAddressResolved } else { [string]$Config.GatewayLanBindAddress }
        return "${address}:$Port"
    }
    if ($Name -eq 'admin-web') {
        $address = if ($Config.ContainsKey('AdminWebBindAddress')) { [string]$Config.AdminWebBindAddress } else { '127.0.0.1' }
        return "${address}:$Port"
    }
    if ($Config.ContainsKey('LanMode') -and [bool]$Config.LanMode) {
        return Get-LanServiceListenerAddress $Config $Port
    }
    $address = if ($Config.ContainsKey('BindAddress')) { [string]$Config.BindAddress } else { '127.0.0.1' }
    return "${address}:$Port"
}

function Test-ManagedServiceRunning($Config, [string]$Name, [int]$Port) {
    $record = Test-RecordedProcess $Config $Name
    if (-not $record -or -not $record.Valid) { return $false }
    $runtimeIdentity = Test-ManagedServiceRuntimeIdentity $Config $record.Record
    if (-not $runtimeIdentity.Valid) { return $false }
    $listeners = @(Get-TcpListeningConnection $Port)
    $owners = @(if ($listeners.Count -gt 0) { @($listeners | Select-Object -ExpandProperty OwningProcess -Unique) } else { @(Get-PortOwner $Port) })
    $listenerPid = if ($record.ListenerProcess) { [int]$record.ListenerProcess.Id } else { 0 }
    if ($listenerPid -gt 0) {
        if ($owners.Count -ne 1 -or $owners[0] -ne $listenerPid) { return $false }
    } elseif ($listeners.Count -eq 0 -or -not $record.Process -or @($owners | Where-Object { Test-ProcessDescendantOf $_ $record.Process.Id }).Count -ne $owners.Count) {
        return $false
    }
    $expected = Get-ManagedServiceExpectedListenerAddress $Config $Name $Port
    $expectedHost = $expected.Substring(0, $expected.LastIndexOf(':'))
    if ($listeners.Count -gt 0 -and @($listeners | Where-Object { [string]$_.LocalAddress -eq $expectedHost }).Count -ne $listeners.Count) { return $false }
    return Test-HttpOk (Get-ManagedServiceHealthUrl $Config $Name $Port)
}

function Get-ProcessMetadata([int]$Id, [int]$TimeoutMilliseconds = 1500) {
    if ($Id -le 0) { return $null }
    $searcher = $null
    $results = $null
    try {
        $options = [System.Management.EnumerationOptions]::new()
        $options.ReturnImmediately = $true
        $options.Rewindable = $false
        $options.Timeout = [TimeSpan]::FromMilliseconds($TimeoutMilliseconds)
        $scope = [System.Management.ManagementScope]::new('\\.\root\cimv2')
        $query = [System.Management.ObjectQuery]::new("SELECT ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate FROM Win32_Process WHERE ProcessId = $Id")
        $searcher = [System.Management.ManagementObjectSearcher]::new($scope, $query, $options)
        $results = $searcher.Get()
        $item = @($results | Select-Object -First 1)
        if ($item.Count -eq 0) { return $null }
        return [pscustomobject]@{
            ProcessId = [int]$item[0].ProcessId
            ParentProcessId = [int]$item[0].ParentProcessId
            ExecutablePath = [string]$item[0].ExecutablePath
            CommandLine = [string]$item[0].CommandLine
            CreationDate = [string]$item[0].CreationDate
        }
    } catch {
        return $null
    } finally {
        if ($null -ne $results) { $results.Dispose() }
        if ($null -ne $searcher) { $searcher.Dispose() }
    }
}

function Get-ProcessMetadataSnapshot([int]$TimeoutMilliseconds = 2000) {
    $searcher = $null
    $results = $null
    try {
        $options = [System.Management.EnumerationOptions]::new()
        $options.ReturnImmediately = $true
        $options.Rewindable = $false
        $options.Timeout = [TimeSpan]::FromMilliseconds($TimeoutMilliseconds)
        $scope = [System.Management.ManagementScope]::new('\\.\root\cimv2')
        $query = [System.Management.ObjectQuery]::new('SELECT ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate FROM Win32_Process')
        $searcher = [System.Management.ManagementObjectSearcher]::new($scope, $query, $options)
        $results = $searcher.Get()
        return @($results | ForEach-Object {
            [pscustomobject]@{
                ProcessId = [int]$_.ProcessId
                ParentProcessId = [int]$_.ParentProcessId
                ExecutablePath = [string]$_.ExecutablePath
                CommandLine = [string]$_.CommandLine
                CreationDate = [string]$_.CreationDate
            }
        })
    } catch {
        return @()
    } finally {
        if ($null -ne $results) { $results.Dispose() }
        if ($null -ne $searcher) { $searcher.Dispose() }
    }
}

function Test-ProcessDescendantOf([int]$ProcessId, [int]$AncestorProcessId) {
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt 32; $depth++) {
        if ($currentId -eq $AncestorProcessId) { return $true }
        $metadata = Get-ProcessMetadata $currentId
        if ($null -eq $metadata -or [int]$metadata.ParentProcessId -le 0) { return $false }
        $currentId = [int]$metadata.ParentProcessId
    }
    return $false
}

function Get-ProcessIdentitySummary([int]$Id) {
    $metadata = Get-ProcessMetadata $Id
    if ($null -eq $metadata) { return "PID $Id（无法读取进程信息）" }
    $path = if ([string]::IsNullOrWhiteSpace([string]$metadata.ExecutablePath)) { '<未知路径>' } else { [string]$metadata.ExecutablePath }
    $command = if ([string]::IsNullOrWhiteSpace([string]$metadata.CommandLine)) { '<未知命令>' } else { [string]$metadata.CommandLine }
    return "PID $Id；路径：$path；命令：$command"
}

function Get-CommandFeatureSha256([string]$Value) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-RepositoryRuntimeIdentity([string]$RepositoryRoot) {
    if ([string]::IsNullOrWhiteSpace($RepositoryRoot) -or -not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
        return [pscustomobject]@{ Available=$false; RepositoryRoot=$RepositoryRoot; GitSha=$null; SourceState='UNAVAILABLE'; SourceFingerprint=$null; Reason='RepositoryRoot 不存在或未配置' }
    }
    try {
        $configuredRoot = [IO.Path]::GetFullPath($RepositoryRoot)
        $gitRoot = [string](& git -C $configuredRoot rev-parse --show-toplevel 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitRoot)) { throw '无法解析 Git 仓库根目录' }
        $gitRoot = [IO.Path]::GetFullPath($gitRoot.Trim())
        if (-not [string]::Equals($gitRoot, $configuredRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'RepositoryRoot 不是 Git 工作树根目录' }

        $gitSha = [string](& git -C $gitRoot rev-parse HEAD 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or $gitSha -notmatch '^[0-9a-fA-F]{40}$') { throw '无法解析 Git HEAD' }
        $statusLines = @(& git -C $gitRoot status --porcelain=v1 --untracked-files=all 2>$null)
        if ($LASTEXITCODE -ne 0) { throw '无法读取 Git 工作树状态' }
        # Disable safecrlf diagnostics only for this read-only fingerprint command:
        # PowerShell treats Git's line-ending warning as a terminating native error.
        $diffLines = @(& git -c core.safecrlf=false -C $gitRoot diff --no-ext-diff --binary HEAD 2>$null)
        if ($LASTEXITCODE -ne 0) { throw '无法读取 Git 工作树差异' }
        $untrackedFiles = @(& git -C $gitRoot ls-files --others --exclude-standard 2>$null)
        if ($LASTEXITCODE -ne 0) { throw '无法读取 Git 未跟踪文件列表' }

        # Only an opaque digest is persisted. It detects tracked edits and
        # untracked-file content changes without writing source content to records.
        $fingerprintParts = [Collections.Generic.List[string]]::new()
        $fingerprintParts.Add("head=$($gitSha.Trim().ToLowerInvariant())")
        $fingerprintParts.Add("status=$($statusLines -join "`n")")
        $fingerprintParts.Add("diff=$($diffLines -join "`n")")
        foreach ($relativePath in @($untrackedFiles | Sort-Object)) {
            $candidatePath = [IO.Path]::GetFullPath((Join-Path $gitRoot $relativePath))
            if (-not $candidatePath.StartsWith($gitRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Git 未跟踪文件路径超出仓库根目录' }
            if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { throw '无法读取 Git 未跟踪文件' }
            $fingerprintParts.Add("untracked=${relativePath}:$((Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant())")
        }
        return [pscustomobject]@{
            Available=$true
            RepositoryRoot=$gitRoot
            GitSha=$gitSha.Trim().ToLowerInvariant()
            SourceState=if ($statusLines.Count -eq 0) { 'CLEAN' } else { 'DIRTY' }
            SourceFingerprint=(Get-CommandFeatureSha256 ($fingerprintParts -join "`n"))
            Reason='已解析'
        }
    } catch {
        return [pscustomobject]@{ Available=$false; RepositoryRoot=$RepositoryRoot; GitSha=$null; SourceState='UNAVAILABLE'; SourceFingerprint=$null; Reason=$_.Exception.Message }
    }
}

function Test-ManagedServiceRuntimeIdentity($Config, $Record) {
    $requiredFields = @('repository_root','repository_git_sha','repository_source_state','repository_source_fingerprint','runtime_mode','network_mode')
    if ($null -eq $Record -or @($requiredFields | Where-Object { $Record.PSObject.Properties.Name -notcontains $_ }).Count -gt 0) {
        return [pscustomobject]@{ Valid=$false; Reason='运行记录缺少仓库版本身份字段'; Current=$null }
    }
    $repositoryRoot = if ($Config.ContainsKey('RepositoryRoot')) { [string]$Config.RepositoryRoot } else { '' }
    $current = Get-RepositoryRuntimeIdentity $repositoryRoot
    if (-not $current.Available) {
        return [pscustomobject]@{ Valid=$false; Reason="当前仓库版本身份不可用：$($current.Reason)"; Current=$current }
    }
    $expectedMode = Get-ConfiguredRuntimeMode $Config
    $sameRoot = [string]::Equals([IO.Path]::GetFullPath([string]$Record.repository_root), $current.RepositoryRoot, [StringComparison]::OrdinalIgnoreCase)
    $sameSha = [string]::Equals([string]$Record.repository_git_sha, $current.GitSha, [StringComparison]::OrdinalIgnoreCase)
    $sameFingerprint = [string]::Equals([string]$Record.repository_source_fingerprint, $current.SourceFingerprint, [StringComparison]::OrdinalIgnoreCase)
    $sameMode = [string]$Record.runtime_mode -eq $expectedMode
    $networkModeRecorded = [string]$Record.network_mode -in @('LOCAL', 'LAN')
    if ($sameRoot -and $sameSha -and $sameFingerprint -and $sameMode -and $networkModeRecorded) {
        return [pscustomobject]@{ Valid=$true; Reason='仓库版本身份已验证'; Current=$current }
    }
    return [pscustomobject]@{ Valid=$false; Reason="repositoryRoot=$sameRoot; gitSha=$sameSha; sourceFingerprint=$sameFingerprint; runtimeMode=$sameMode; networkModeRecorded=$networkModeRecorded"; Current=$current }
}

function Assert-ManagedRuntimeSourceConsistency($Config, $Services) {
    $mismatches = [Collections.Generic.List[string]]::new()
    foreach ($service in @($Services)) {
        $check = Test-RecordedProcess $Config ([string]$service.Name)
        if ($check -and $check.Valid) {
            $identity = Test-ManagedServiceRuntimeIdentity $Config $check.Record
            if (-not $identity.Valid) { $mismatches.Add("$($service.Name)：$($identity.Reason)") }
        }
    }
    if ($mismatches.Count -gt 0) {
        throw "已登记服务不是当前仓库版本或缺少版本身份：$($mismatches -join '；')。请先使用停止AI客服.bat 安全停止已验证服务，再重新启动；不会按端口结束未知进程。"
    }
}

function Get-RecordedListenerCheck($Config, $Record) {
    $requiredFields = @('managed_pid','listener_pid','listener_executable_path','listener_started_at','listener_parent_pid')
    if (@($requiredFields | Where-Object { $Record.PSObject.Properties.Name -notcontains $_ }).Count -gt 0) {
        return [pscustomobject]@{ Present = $false; Valid = $false; Reason = '记录未包含监听 PID 身份字段'; Process = $null }
    }
    $listenerPid = 0
    if (-not [int]::TryParse([string]$Record.listener_pid, [ref]$listenerPid) -or $listenerPid -le 0) {
        return [pscustomobject]@{ Present = $true; Valid = $false; Reason = '监听 PID 无效'; Process = $null }
    }
    $listenerProcess = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
    if (-not $listenerProcess) { return [pscustomobject]@{ Present = $true; Valid = $false; Reason = '监听 PID 已退出'; Process = $null } }
    $metadata = Get-ProcessMetadata $listenerPid
    $listenerPath = if ($metadata -and -not [string]::IsNullOrWhiteSpace([string]$metadata.ExecutablePath)) { [string]$metadata.ExecutablePath } else { [string]$listenerProcess.Path }
    $samePath = -not [string]::IsNullOrWhiteSpace($listenerPath) -and [string]::Equals([IO.Path]::GetFullPath($listenerPath), [IO.Path]::GetFullPath([string]$Record.listener_executable_path), [StringComparison]::OrdinalIgnoreCase)
    $sameStart = $listenerProcess.StartTime.ToUniversalTime().ToString('o') -eq [string]$Record.listener_started_at
    $sameParent = [int]$Record.listener_parent_pid -eq 0 -or ($metadata -and [int]$metadata.ParentProcessId -eq [int]$Record.listener_parent_pid)
    $commandLineVisible = $metadata -and -not [string]::IsNullOrWhiteSpace([string]$metadata.CommandLine)
    $hasFeature = $commandLineVisible -and $metadata.CommandLine.IndexOf([string]$Record.commandFeature, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $listenerCommandValid = [string]$Record.name -eq 'admin-web' -or -not $commandLineVisible -or $hasFeature
    $owners = @(Get-PortOwner ([int]$Record.port))
    $ownsPort = $owners.Count -eq 1 -and [int]$owners[0] -eq $listenerPid
    $valid = $samePath -and $sameStart -and $sameParent -and $listenerCommandValid -and $ownsPort
    $reason = if ($valid) { '监听 PID 已验证' } else { "listenerPath=$samePath; listenerStarted=$sameStart; listenerParent=$sameParent; listenerCommand=$listenerCommandValid; listenerPort=$ownsPort" }
    return [pscustomobject]@{ Present = $true; Valid = $valid; Reason = $reason; Process = $listenerProcess }
}

function Test-RecordedProcess($Config, [string]$Name, [switch]$Detailed) {
    $path = Get-ServiceRecordPath $Config $Name
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return [pscustomobject]@{ Valid = $false; Reason = '运行记录无法解析'; Record = $null; Process = $null; ListenerProcess = $null } }
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    $metadata = if ($process) { Get-ProcessMetadata $process.Id } else { $null }
    $actualExecutablePath = if ($metadata -and -not [string]::IsNullOrWhiteSpace($metadata.ExecutablePath)) { [string]$metadata.ExecutablePath } elseif ($process) { [string]$process.Path } else { '' }
    $sameExecutable = $process -and -not [string]::IsNullOrWhiteSpace($actualExecutablePath) -and [string]::Equals([IO.Path]::GetFullPath($actualExecutablePath), [IO.Path]::GetFullPath($record.executablePath), [StringComparison]::OrdinalIgnoreCase)
    $canVerifyCommandLine = $metadata -and -not [string]::IsNullOrWhiteSpace($metadata.CommandLine)
    $hasFeature = $canVerifyCommandLine -and $metadata.CommandLine.IndexOf([string]$record.commandFeature, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $recordedStart = ([datetime]$record.startedUtc).ToUniversalTime().ToString('o')
    $sameStart = $process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $recordedStart
    $sameParent = $true
    if ($record.PSObject.Properties.Name -contains 'parentProcessId' -and [int]$record.parentProcessId -gt 0) {
        $sameParent = $metadata -and [int]$metadata.ParentProcessId -eq [int]$record.parentProcessId
    }
    $featureIntegrity = -not ($record.PSObject.Properties.Name -contains 'commandFeatureSha256') -or [string]$record.commandFeatureSha256 -eq (Get-CommandFeatureSha256 ([string]$record.commandFeature))
    $adminRecordValid = $true
    if ($Name -eq 'admin-web') {
        $requiredAdminFields = @('service_name','managed_pid','listener_pid','parent_pid','creation_time','executable_path','command_summary','working_directory','bind_address','port','url','started_at')
        $adminRecordValid = @($requiredAdminFields | Where-Object { $record.PSObject.Properties.Name -notcontains $_ }).Count -eq 0
        if ($adminRecordValid) {
            $listenerPid = 0
            $adminRecordValid =
                [int]::TryParse([string]$record.listener_pid, [ref]$listenerPid) -and $listenerPid -gt 0 -and
                [string]$record.service_name -eq 'admin-web' -and
                [int]$record.managed_pid -eq [int]$record.pid -and
                [int]$record.parent_pid -eq [int]$record.parentProcessId -and
                [string]$record.executable_path -eq [string]$record.executablePath -and
                [string]$record.command_summary -eq [string]$record.commandSummary -and
                [string]$record.working_directory -eq [string]$record.workingDirectory -and
                [string]$record.started_at -eq [string]$record.startedUtc -and
                [int]$record.port -eq [int]$Config.AdminWebPort -and
                [string]$record.bind_address -eq [string]$Config.AdminWebBindAddress -and
                [string]$record.url -eq [string]$Config.AdminWebUrl -and
                [IO.Path]::GetFullPath([string]$record.working_directory) -eq [IO.Path]::GetFullPath((Join-Path $Config.RepositoryRoot 'admin_web'))
            if ($adminRecordValid) {
                $listenerOwners = @(Get-PortOwner ([int]$record.port))
                $listenerProcess = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
                $listenerMetadata = if ($listenerProcess) { Get-ProcessMetadata $listenerPid } else { $null }
                $listenerPath = if ($listenerMetadata -and -not [string]::IsNullOrWhiteSpace([string]$listenerMetadata.ExecutablePath)) { [string]$listenerMetadata.ExecutablePath } elseif ($listenerProcess) { [string]$listenerProcess.Path } else { '' }
                $listenerStartMatches = $listenerProcess -and $record.PSObject.Properties.Name -contains 'listener_started_at' -and $listenerProcess.StartTime.ToUniversalTime().ToString('o') -eq [string]$record.listener_started_at
                $listenerPathMatches = $record.PSObject.Properties.Name -contains 'listener_executable_path' -and -not [string]::IsNullOrWhiteSpace($listenerPath) -and [string]::Equals([IO.Path]::GetFullPath($listenerPath), [IO.Path]::GetFullPath([string]$record.listener_executable_path), [StringComparison]::OrdinalIgnoreCase)
                $adminRecordValid = $listenerOwners -contains $listenerPid -and $listenerStartMatches -and $listenerPathMatches
            }
        }
    }
    $listenerCheck = Get-RecordedListenerCheck $Config $record
    $managedValid = $sameExecutable -and $sameStart -and $sameParent -and ($hasFeature -or -not $canVerifyCommandLine) -and $featureIntegrity
    if ($listenerCheck.Present -and $listenerCheck.Valid -and $featureIntegrity -and $adminRecordValid -and ((-not $process) -or $managedValid)) {
        $reason = if ($process) { '受管 PID 与监听 PID 已验证' } else { '受管启动包装层已退出，监听 PID 已验证' }
        return [pscustomobject]@{ Valid = $true; Reason = $reason; Record = $record; Process = $process; ListenerProcess = $listenerCheck.Process }
    }
    if ($managedValid -and $adminRecordValid -and -not $listenerCheck.Present) {
        $reason = if ($hasFeature) { '已验证' } else { '已验证（系统未公开命令行，使用可执行路径和启动时间）' }
        return [pscustomobject]@{ Valid = $true; Reason = $reason; Record = $record; Process = $process; ListenerProcess = $null }
    }
    $details = "managedPresent=$($null -ne $process); executable=$sameExecutable; started=$sameStart; parent=$sameParent; command=$($hasFeature -or -not $canVerifyCommandLine); featureIntegrity=$featureIntegrity; listener=$($listenerCheck.Reason); admin=$adminRecordValid"
    return [pscustomobject]@{ Valid = $false; Reason = "PID、父子关系、可执行路径、启动时间或命令特征不匹配（$details）"; Record = $record; Process = $process; ListenerProcess = $listenerCheck.Process }
}

function Save-ServiceRecord($Config, [string]$Name, $Process, [string]$ExecutablePath, [string]$WorkingDirectory, [string]$CommandSummary, [string]$CommandFeature, [int]$Port) {
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory, (Get-ServiceLogDirectory $Config) | Out-Null
    $startedUtc = $null
    foreach ($attempt in 1..3) {
        try {
            $Process.Refresh()
            $startedUtc = $Process.StartTime.ToUniversalTime().ToString('o')
        } catch {
            $Process = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$startedUtc)) { break }
        if ($null -eq $Process) { break }
        Start-Sleep -Milliseconds 50
    }
    if ([string]::IsNullOrWhiteSpace([string]$startedUtc)) { throw "$Name 启动进程身份尚不可用，拒绝建立运行记录。" }
    $metadata = Get-ProcessMetadata $Process.Id
    $parentProcessId = if ($metadata) { [int]$metadata.ParentProcessId } else { 0 }
    $repositoryRoot = if ($Config.ContainsKey('RepositoryRoot')) { [string]$Config.RepositoryRoot } else { '' }
    $runtimeIdentity = Get-RepositoryRuntimeIdentity $repositoryRoot
    $runtimeMode = Get-ConfiguredRuntimeMode $Config
    $networkMode = Get-ConfiguredNetworkMode $Config
    $record = [ordered]@{ name=$Name; pid=$Process.Id; parentProcessId=$parentProcessId; managed_pid=$Process.Id; executablePath=[IO.Path]::GetFullPath($ExecutablePath); workingDirectory=[IO.Path]::GetFullPath($WorkingDirectory); startedUtc=$startedUtc; commandSummary=$CommandSummary; commandFeature=$CommandFeature; commandFeatureSha256=(Get-CommandFeatureSha256 $CommandFeature); port=$Port; healthUrl=(Get-ManagedServiceHealthUrl $Config $Name $Port); logDirectory=(Get-ServiceLogDirectory $Config); repository_root=$runtimeIdentity.RepositoryRoot; repository_git_sha=$runtimeIdentity.GitSha; repository_source_state=$runtimeIdentity.SourceState; repository_source_fingerprint=$runtimeIdentity.SourceFingerprint; runtime_mode=$runtimeMode; network_mode=$networkMode }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Get-ServiceRecordPath $Config $Name) -Encoding UTF8
}

function Update-ManagedServiceListenerRecord($Config, [string]$Name) {
    $recordPath = Get-ServiceRecordPath $Config $Name
    $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $owners = @(Get-PortOwner ([int]$record.port))
    if ($owners.Count -ne 1) { throw "$Name 端口 $($record.port) 的监听 PID 数量异常：$($owners -join ', ')。" }
    $listenerPid = [int]$owners[0]
    $listenerProcess = Get-Process -Id $listenerPid -ErrorAction Stop
    $listenerMetadata = Get-ProcessMetadata $listenerPid
    $listenerPath = if ($listenerMetadata -and -not [string]::IsNullOrWhiteSpace([string]$listenerMetadata.ExecutablePath)) { [string]$listenerMetadata.ExecutablePath } else { [string]$listenerProcess.Path }
    if ([string]::IsNullOrWhiteSpace($listenerPath)) { throw "$Name 无法读取监听 PID $listenerPid 的可执行路径，拒绝建立运行记录。" }
    if ($Name -ne 'admin-web' -and $listenerMetadata -and -not [string]::IsNullOrWhiteSpace([string]$listenerMetadata.CommandLine) -and $listenerMetadata.CommandLine.IndexOf([string]$record.commandFeature, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "$Name 监听 PID $listenerPid 的命令特征无法验证，拒绝建立运行记录。"
    }
    $record | Add-Member -NotePropertyName listener_pid -NotePropertyValue $listenerPid -Force
    $record | Add-Member -NotePropertyName listener_executable_path -NotePropertyValue ([IO.Path]::GetFullPath($listenerPath)) -Force
    $record | Add-Member -NotePropertyName listener_started_at -NotePropertyValue ($listenerProcess.StartTime.ToUniversalTime().ToString('o')) -Force
    $listenerParentPid = if ($listenerMetadata) { [int]$listenerMetadata.ParentProcessId } else { 0 }
    $record | Add-Member -NotePropertyName listener_parent_pid -NotePropertyValue $listenerParentPid -Force
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    return $record
}

function Update-AdminWebServiceRecord($Config, $Process) {
    $recordPath = Get-ServiceRecordPath $Config 'admin-web'
    $record = Update-ManagedServiceListenerRecord $Config 'admin-web'
    $managedMetadata = Get-ProcessMetadata $Process.Id
    $managedPath = if ($managedMetadata -and -not [string]::IsNullOrWhiteSpace([string]$managedMetadata.ExecutablePath)) { [string]$managedMetadata.ExecutablePath } else { [string]$Process.Path }
    if ([string]::IsNullOrWhiteSpace($managedPath)) { throw "无法读取 Admin 后台受管 PID $($Process.Id) 的可执行路径，拒绝建立运行记录。" }
    $managedPath = [IO.Path]::GetFullPath($managedPath)
    $record | Add-Member -NotePropertyName service_name -NotePropertyValue 'admin-web' -Force
    $record | Add-Member -NotePropertyName managed_pid -NotePropertyValue ([int]$record.pid) -Force
    $record | Add-Member -NotePropertyName executablePath -NotePropertyValue $managedPath -Force
    $record | Add-Member -NotePropertyName parent_pid -NotePropertyValue ([int]$record.parentProcessId) -Force
    $record | Add-Member -NotePropertyName creation_time -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    $record | Add-Member -NotePropertyName executable_path -NotePropertyValue $managedPath -Force
    $record | Add-Member -NotePropertyName command_summary -NotePropertyValue ([string]$record.commandSummary) -Force
    $record | Add-Member -NotePropertyName working_directory -NotePropertyValue ([string]$record.workingDirectory) -Force
    $record | Add-Member -NotePropertyName bind_address -NotePropertyValue ([string]$Config.AdminWebBindAddress) -Force
    $record | Add-Member -NotePropertyName url -NotePropertyValue ([string]$Config.AdminWebUrl) -Force
    $record | Add-Member -NotePropertyName started_at -NotePropertyValue ([string]$record.startedUtc) -Force
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    return $record
}

function Get-ProcessDescendantIds([int]$ProcessId) {
    $allProcesses = @(Get-ProcessMetadataSnapshot)
    if ($allProcesses.Count -eq 0) { return @() }
    $queue = [Collections.Generic.Queue[int]]::new()
    $queue.Enqueue($ProcessId)
    $descendants = [Collections.Generic.List[int]]::new()
    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()
        foreach ($child in @($allProcesses | Where-Object { [int]$_.ParentProcessId -eq $parentId })) {
            $childId = [int]$child.ProcessId
            if (-not $descendants.Contains($childId)) {
                $descendants.Add($childId)
                $queue.Enqueue($childId)
            }
        }
    }
    return @($descendants)
}

function Stop-VerifiedProcessTree([int]$ProcessId, [int]$ListenerProcessId = 0) {
    $descendants = @(Get-ProcessDescendantIds $ProcessId)
    $processIds = @($descendants | Sort-Object -Descending) + @($ListenerProcessId, $ProcessId) | Where-Object { $_ -gt 0 } | Select-Object -Unique
    foreach ($id in $processIds) {
        if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
            try {
                Stop-Process -Id $id -ErrorAction Stop
            } catch {
                # A verified child may exit after the existence check. Treat only
                # that completed exit as success; preserve real stop failures.
                if (Get-Process -Id $id -ErrorAction SilentlyContinue) { throw }
            }
        }
    }
    Start-Sleep -Milliseconds 500
    return @($processIds | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
}

function Get-TcpListeningConnection([int]$Port) {
    $netstat = Join-Path $env:SystemRoot 'System32\netstat.exe'
    $lines = @(& $netstat -ano -p tcp)
    if ($LASTEXITCODE -ne 0) { throw '无法读取 TCP 监听状态；为避免错误启动或停止进程，操作已拒绝。' }
    $listeners = @()
    foreach ($line in $lines) {
        $columns = @(([string]$line).Trim() -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        if ($columns.Count -lt 5 -or [string]$columns[0] -ne 'TCP' -or [string]$columns[3] -ne 'LISTENING') { continue }
        $localEndpoint = [string]$columns[1]
        $separator = $localEndpoint.LastIndexOf(':')
        if ($separator -lt 1) { continue }
        $localPort = 0
        if (-not [int]::TryParse($localEndpoint.Substring($separator + 1), [ref]$localPort) -or $localPort -ne $Port) { continue }
        $owningProcess = 0
        if (-not [int]::TryParse([string]$columns[4], [ref]$owningProcess) -or $owningProcess -le 0) { continue }
        $listeners += [pscustomobject]@{ LocalAddress=$localEndpoint.Substring(0, $separator); LocalPort=$localPort; OwningProcess=$owningProcess }
    }
    return @($listeners | Sort-Object LocalAddress, OwningProcess -Unique)
}

function Get-PortOwner([int]$Port) {
    return @(Get-TcpListeningConnection $Port | Select-Object -ExpandProperty OwningProcess -Unique)
}
function Assert-PortAvailable($Config, [string]$Name, [int]$Port) {
    $owners = @(Get-PortOwner $Port)
    if ($owners.Count -eq 0) { return }
    $record = Test-RecordedProcess $Config $Name
    if ($record -and $record.Valid -and $record.ListenerProcess -and $owners.Count -eq 1 -and [int]$owners[0] -eq [int]$record.ListenerProcess.Id) {
        throw "$Name 已由本工具启动（登记 PID $($record.Process.Id)，监听 PID $($owners -join ', ')，端口 $Port）。请使用检查脚本，或先停止后再启动。"
    }
    if ($record -and $record.Valid -and $record.Process -and @($owners | Where-Object { Test-ProcessDescendantOf $_ $record.Process.Id }).Count -eq $owners.Count) {
        throw "$Name 已由本工具启动（登记 PID $($record.Process.Id)，监听 PID $($owners -join ', ')，端口 $Port）。请使用检查脚本，或先停止后再启动。"
    }
    $identity = @($owners | ForEach-Object { Get-ProcessIdentitySummary $_ }) -join '；'
    throw "端口 $Port 已被未知或未验证进程占用（$identity）。为避免误杀，启动已停止；请人工处理该进程。"
}

function Test-HttpOk([string]$Url) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3; return $r.StatusCode -ge 200 -and $r.StatusCode -lt 400 } catch { return $false } }

function Get-ParallelHttpHealth([object[]]$Endpoints, [int]$TimeoutMilliseconds = 3000) {
    if ($TimeoutMilliseconds -lt 100 -or $TimeoutMilliseconds -gt 30000) {
        throw 'HTTP健康检查超时必须在100-30000毫秒之间。'
    }
    $pending = @()
    foreach ($endpoint in @($Endpoints)) {
        $request = [System.Net.HttpWebRequest]::Create([string]$endpoint.Url)
        $request.Method = 'GET'
        $request.Timeout = $TimeoutMilliseconds
        $request.ReadWriteTimeout = $TimeoutMilliseconds
        $pending += [pscustomobject]@{
            Name = [string]$endpoint.Name
            Url = [string]$endpoint.Url
            Request = $request
            Async = $request.BeginGetResponse($null, $null)
        }
    }

    $results = @{}
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    foreach ($probe in $pending) {
        $response = $null
        try {
            $remainingMilliseconds = [Math]::Max(
                0,
                [int][Math]::Ceiling(($deadline - [DateTime]::UtcNow).TotalMilliseconds)
            )
            if (-not $probe.Async.AsyncWaitHandle.WaitOne($remainingMilliseconds)) {
                $probe.Request.Abort()
                throw "${TimeoutMilliseconds}ms超时"
            }
            $response = $probe.Request.EndGetResponse($probe.Async)
            $statusCode = [int]$response.StatusCode
            $results[$probe.Name] = [pscustomobject]@{
                Name = $probe.Name
                Url = $probe.Url
                Ok = ($statusCode -ge 200 -and $statusCode -lt 400)
                StatusCode = $statusCode
                Error = ''
            }
        } catch {
            $results[$probe.Name] = [pscustomobject]@{
                Name = $probe.Name
                Url = $probe.Url
                Ok = $false
                StatusCode = 0
                Error = $_.Exception.Message
            }
        } finally {
            if ($null -ne $response) { $response.Dispose() }
            $probe.Async.AsyncWaitHandle.Dispose()
        }
    }
    return $results
}
function Wait-HttpOk([string]$Url, [int]$Seconds, [string]$Label) { for ($i=0; $i -lt $Seconds; $i++) { if (Test-HttpOk $Url) { return }; Start-Sleep -Seconds 1 }; throw "$Label 未在 $Seconds 秒内就绪：$Url。请查看运行日志。" }

function Assert-AdminWebDependenciesLegacy($Config) {
    $adminDirectory = Join-Path $Config.RepositoryRoot 'admin_web'
    $packagePath = Join-Path $adminDirectory 'package.json'
    $lockPath = Join-Path $adminDirectory 'pnpm-lock.yaml'
    $nodeModulesPath = Join-Path $adminDirectory 'node_modules'
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { throw 'Admin 后台缺少 Node.js（node.exe）。脚本不会自动安装。' }
    if (-not (Get-Command $Config.PnpmCommand -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $Config.PnpmCommand -PathType Leaf)) {
        throw "Admin 后台 PnpmCommand 不可用：$($Config.PnpmCommand)。脚本不会自动安装。"
    }
    & $Config.PnpmCommand --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Admin 后台 pnpm 无法执行。脚本不会自动安装依赖。' }
    if (-not (Test-Path -LiteralPath $adminDirectory -PathType Container)) { throw "缺少 admin_web 目录：$adminDirectory" }
    if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) { throw "缺少 admin_web/package.json：$packagePath" }
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) { throw "缺少 admin_web 的 pnpm 锁文件：$lockPath" }
    if (-not (Test-Path -LiteralPath $nodeModulesPath -PathType Container)) { throw "缺少 admin_web/node_modules：$nodeModulesPath。请人工安装依赖。" }
    try { $package = Get-Content -LiteralPath $packagePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw "admin_web/package.json 无法解析：$($_.Exception.Message)" }
    if ($null -eq $package.scripts -or [string]::IsNullOrWhiteSpace([string]$package.scripts.dev)) { throw 'admin_web/package.json 缺少真实 dev package script。' }
    return [pscustomobject]@{ Directory=$adminDirectory; PackagePath=$packagePath; PnpmExecutable=(Get-Command $Config.PnpmCommand -ErrorAction Stop).Source }
}

function Assert-ProductionWebDependencies($Config, [ValidateSet('frontend','admin_web')] [string]$DirectoryName) {
    $directory = Join-Path $Config.RepositoryRoot $DirectoryName
    $distDirectory = Join-Path $directory 'dist'
    $indexPath = Join-Path $distDirectory 'index.html'
    $serverPath = Join-Path $PSScriptRoot 'serve_ai_cs_web.py'
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "缺少 $DirectoryName 目录：$directory" }
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { throw "$DirectoryName 缺少生产构建产物 dist/index.html；请在发布流水线执行 build，Runtime 禁止启动 Vite dev server。" }
    if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) { throw "缺少生产 Web Server：$serverPath" }
    & $Config.PlatformPythonPath $serverPath --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Production Web Server 无法由 Platform Python 执行。' }
    return [pscustomobject]@{ Directory=$directory; DistDirectory=$distDirectory; ServerPath=$serverPath }
}

function Assert-AdminWebDependencies($Config) {
    return Assert-ProductionWebDependencies $Config 'admin_web'
}

function Start-ProductionWebService($Config, [string]$Name, [string]$DirectoryName, [string]$BindAddress, [int]$Port, [string]$Url, [string[]]$ProxyMappings) {
    $dependency = Assert-ProductionWebDependencies $Config $DirectoryName
    Assert-PortAvailable $Config $Name $Port
    $arguments = @($dependency.ServerPath, '--root', $dependency.DistDirectory, '--bind-address', $BindAddress, '--port', [string]$Port, '--allowed-host', ([uri]$Url).Host)
    if (([uri]$Url).Scheme -eq 'https') {
        $certificatePath = [string]$Config.CustomerWebTlsCertificateReference
        $keyPath = [string]$Config.CustomerWebTlsKeyReference
        foreach ($path in @($certificatePath, $keyPath)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Customer Web TLS 文件不存在：$path" } }
        $arguments += @('--tls-cert', $certificatePath, '--tls-key', $keyPath)
    }
    foreach ($mapping in $ProxyMappings) { $arguments += @('--proxy', $mapping) }
    return Start-ManagedServiceWithEnvironment $Config $Name $Config.PlatformPythonPath $arguments $dependency.Directory 'serve_ai_cs_web.py' $Port @{}
}

function Start-CustomerWebService($Config) {
    $bindAddress = if ($Config.ContainsKey('CustomerWebBindAddress')) { [string]$Config.CustomerWebBindAddress } else { [string]$Config.BindAddress }
    $process = Start-ProductionWebService $Config 'customer-web' 'frontend' $bindAddress ([int]$Config.CustomerWebPort) ([string]$Config.CustomerWebUrl) @(
        "/platform-api=http://127.0.0.1:$($Config.PlatformPort)",
        "/rag-api=http://127.0.0.1:$($Config.RagPort)"
    )
    Wait-HttpOk ([string]$Config.CustomerWebUrl) 45 '客服页面'
    return Update-ManagedServiceListenerRecord $Config 'customer-web'
}

function Start-AdminWebService($Config) {
    if ([bool]$Config.AdminEnableLanMode) {
        Write-Warning "AdminEnableLanMode=true：管理后台将使用 $($Config.AdminWebUrl)。本轮不会创建或修改任何防火墙规则。"
    }
    $process = Start-ProductionWebService $Config 'admin-web' 'admin_web' ([string]$Config.AdminWebBindAddress) ([int]$Config.AdminWebPort) ([string]$Config.AdminWebUrl) @(
        "/platform-api=http://127.0.0.1:$($Config.PlatformPort)",
        "/ai-api=http://127.0.0.1:$($Config.RagPort)"
    )
    Wait-HttpOk ([string]$Config.AdminWebUrl) 45 '管理后台'
    return Update-AdminWebServiceRecord $Config $process
}

function Open-AdminWeb($Config, [switch]$NoLaunch) {
    if (-not (Test-HttpOk ([string]$Config.AdminWebUrl))) { throw "管理后台不可用：$($Config.AdminWebUrl)。请先运行启动AI客服.bat。" }
    if (-not $NoLaunch) { Start-Process ([string]$Config.AdminWebUrl) }
    return [string]$Config.AdminWebUrl
}

function Get-Json([string]$Url, [string]$Label, [hashtable]$Headers = @{}) {
    try { return Invoke-RestMethod -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec 10 } catch { throw "$Label 请求失败：$Url。$($_.Exception.Message)" }
}

function Assert-OllamaReady($Config) {
    $tags = Get-Json "$($Config.OllamaBaseUrl)/api/tags" 'Ollama'
    $model = @($tags.models | Where-Object { [string]$_.name -eq [string]$Config.OllamaModel })
    if ($model.Count -ne 1) { throw "Ollama 模型不存在：$($Config.OllamaModel)。脚本不会下载模型。" }
    return $tags
}

function Assert-PlatformDatabaseReady($Config) {
    $platformDirectory = Join-Path $Config.RepositoryRoot 'platform_backend'
    if (-not (Test-Path -LiteralPath $Config.PlatformDatabasePath -PathType Leaf)) { throw "C 数据库不存在：$($Config.PlatformDatabasePath)。普通启动不会创建数据库。" }
    if ((Get-Item -LiteralPath $Config.PlatformDatabasePath).Length -le 16) { throw "C 数据库为空或损坏：$($Config.PlatformDatabasePath)" }
    Push-Location -LiteralPath $platformDirectory
    try {
        & $Config.PlatformPythonPath -m app.runtime_database_identity validate `
            --database $Config.PlatformDatabasePath `
            --binding $Config.PlatformDatabaseBindingPath `
            --environment-id $Config.PlatformDatabaseEnvironmentId | Out-Null
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) { throw "C 数据库身份或版本校验失败（退出码 $exitCode）；普通启动不会迁移或建库。" }
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

function Get-ServiceStatus($Config, [string]$Name, [int]$Port, [string]$HealthUrl, $HealthProbe = $null) {
    $record = Test-RecordedProcess $Config $Name
    $runtimeIdentity = if ($record -and $record.Record) { Test-ManagedServiceRuntimeIdentity $Config $record.Record } else { $null }
    $serviceProcessId = if ($record -and $record.Record -and ($record.Record.PSObject.Properties.Name -contains 'managed_pid')) { [string]$record.Record.managed_pid } elseif ($record -and $record.Process) { [string]$record.Process.Id } else { '-' }
    $listenerProcessId = if ($record -and $record.ListenerProcess) { [string]$record.ListenerProcess.Id } else { '-' }
    $portOwners = @(Get-PortOwner $Port)
    $ownsPort = $record -and $record.Valid -and (($record.ListenerProcess -and $portOwners.Count -eq 1 -and [int]$portOwners[0] -eq [int]$record.ListenerProcess.Id) -or ($record.Process -and $portOwners.Count -gt 0 -and @($portOwners | Where-Object { Test-ProcessDescendantOf $_ $record.Process.Id }).Count -eq $portOwners.Count))
    $serviceState = if ($ownsPort) { '运行中（RUNNING）' } elseif ($record -and $record.Valid) { '记录存在，未确认监听' } else { '未运行' }
    $healthOk = if ($null -eq $HealthProbe) { Test-HttpOk $HealthUrl } else { [bool]$HealthProbe.Ok }
    $portState = if ($portOwners.Count -gt 0) { "监听（LISTENING；PID $($portOwners -join ', ')）" } elseif ($healthOk) { '监听（LISTENING；health 已确认；未能读取端口 PID）' } else { '未监听' }
    $healthState = if ($healthOk) { '可用' } elseif ($null -ne $HealthProbe -and -not [string]::IsNullOrWhiteSpace([string]$HealthProbe.Error)) { "不可用（$($HealthProbe.Error)）" } else { '不可用（HTTP健康检查失败）' }
    $runtimeIdentityState = if ($null -eq $runtimeIdentity) { '未登记' } elseif ($runtimeIdentity.Valid) { '已验证' } else { '不一致' }
    $runtimeGitShortSha = if ($runtimeIdentity -and $runtimeIdentity.Current -and $runtimeIdentity.Current.GitSha) { $runtimeIdentity.Current.GitSha.Substring(0, 12) } elseif ($record -and $record.Record -and ($record.Record.PSObject.Properties.Name -contains 'repository_git_sha') -and -not [string]::IsNullOrWhiteSpace([string]$record.Record.repository_git_sha)) { ([string]$record.Record.repository_git_sha).Substring(0, [Math]::Min(12, ([string]$record.Record.repository_git_sha).Length)) } else { '不可用' }
    $runtimeSourceState = if ($runtimeIdentity -and $runtimeIdentity.Current) { [string]$runtimeIdentity.Current.SourceState } elseif ($record -and $record.Record -and ($record.Record.PSObject.Properties.Name -contains 'repository_source_state')) { [string]$record.Record.repository_source_state } else { '不可用' }
    $runtimeIdentityDetail = if ($runtimeIdentity) { [string]$runtimeIdentity.Reason } else { '没有运行记录' }
    $recordRuntimeMode = if ($record -and $record.Record -and ($record.Record.PSObject.Properties.Name -contains 'runtime_mode')) { [string]$record.Record.runtime_mode } else { '未登记' }
    $recordNetworkMode = if ($record -and $record.Record -and ($record.Record.PSObject.Properties.Name -contains 'network_mode')) { [string]$record.Record.network_mode } else { '未登记' }
    return [pscustomobject]@{ Name=$Name; State=$serviceState; ProcessId=$serviceProcessId; ManagedProcessId=$serviceProcessId; ListenerProcessId=$listenerProcessId; Port=$Port; PortState=$portState; HealthState=$healthState; RuntimeIdentityState=$runtimeIdentityState; RuntimeGitShortSha=$runtimeGitShortSha; RuntimeSourceState=$runtimeSourceState; RuntimeMode=$recordRuntimeMode; NetworkMode=$recordNetworkMode; RuntimeIdentityDetail=$runtimeIdentityDetail; Record=$record }
}

function Get-TargetPilotHttpProbe([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return [pscustomobject]@{ Url=$Url; Reachable=($response.StatusCode -ge 200 -and $response.StatusCode -lt 400); StatusCode=[int]$response.StatusCode }
    } catch {
        # Do not preserve response bodies or exception details in a pilot report.
        return [pscustomobject]@{ Url=$Url; Reachable=$false; StatusCode=0 }
    }
}

function Test-TargetPilotTcpProbe([string]$TargetHost, [int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync($TargetHost, $Port)
        if (-not $connect.Wait(5000)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-TargetPilotServiceStatuses($Config) {
    return @(
        [pscustomobject]@{ Label='C'; Status=(Get-ServiceStatus $Config 'platform' $Config.PlatformPort (Get-ManagedServiceHealthUrl $Config 'platform')) },
        [pscustomobject]@{ Label='A'; Status=(Get-ServiceStatus $Config 'rag' $Config.RagPort (Get-ManagedServiceHealthUrl $Config 'rag')) },
        [pscustomobject]@{ Label='B'; Status=(Get-ServiceStatus $Config 'customer-web' $Config.CustomerWebPort (Get-ManagedServiceHealthUrl $Config 'customer-web')) },
        [pscustomobject]@{ Label='Admin'; Status=(Get-ServiceStatus $Config 'admin-web' $Config.AdminWebPort (Get-ManagedServiceHealthUrl $Config 'admin-web')) }
    )
}

function Get-TargetPilotFirewallReadiness($Config, [scriptblock]$RuleProvider = $null) {
    $expectedPort = [int]$Config.CustomerWebPort
    $expectedSubnet = if ($Config.ContainsKey('LanSubnet')) { [string]$Config.LanSubnet } else { '' }
    if ($expectedPort -ne 5173) {
        return [pscustomobject]@{ State='UNSUPPORTED_CUSTOMER_PORT'; Ready=$false; ExpectedPort=$expectedPort; ExpectedSubnet=$expectedSubnet }
    }
    if ([string]::IsNullOrWhiteSpace($expectedSubnet)) {
        return [pscustomobject]@{ State='LAN_SUBNET_REQUIRED'; Ready=$false; ExpectedPort=$expectedPort; ExpectedSubnet='' }
    }
    try {
        $rules = @(
            if ($RuleProvider) { & $RuleProvider } else { Get-AICustomerFirewallRules }
        )
    } catch {
        return [pscustomobject]@{ State='FIREWALL_STATE_UNAVAILABLE'; Ready=$false; ExpectedPort=$expectedPort; ExpectedSubnet=$expectedSubnet }
    }
    if ($rules.Count -eq 0) {
        return [pscustomobject]@{ State='FIREWALL_RULE_NOT_CONFIGURED'; Ready=$false; ExpectedPort=$expectedPort; ExpectedSubnet=$expectedSubnet }
    }
    $compliant = @()
    foreach ($rule in $rules) {
        try {
            $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule -ErrorAction Stop
            $addressFilter = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule -ErrorAction Stop
            $enabled = [string]$rule.Enabled -match '^(True|1)$'
            $privateProfile = [string]$rule.Profile -match '(?i)Private|(^|[,\s])2($|[,\s])'
            $portMatches = [string]$portFilter.Protocol -eq 'TCP' -and @($portFilter.LocalPort | ForEach-Object { [string]$_ }) -contains ([string]$expectedPort)
            $subnetMatches = @($addressFilter.RemoteAddress | ForEach-Object { [string]$_ }) -contains $expectedSubnet
            if ($enabled -and [string]$rule.Direction -eq 'Inbound' -and [string]$rule.Action -eq 'Allow' -and $privateProfile -and $portMatches -and $subnetMatches) {
                $compliant += $rule
            }
        } catch {
            continue
        }
    }
    if ($compliant.Count -eq 1) {
        return [pscustomobject]@{ State='SCOPED_5173_PRIVATE_RULE_PRESENT'; Ready=$true; ExpectedPort=$expectedPort; ExpectedSubnet=$expectedSubnet }
    }
    return [pscustomobject]@{ State='FIREWALL_RULE_NONCOMPLIANT'; Ready=$false; ExpectedPort=$expectedPort; ExpectedSubnet=$expectedSubnet }
}

function Get-TargetPilotOpsEventPath($Config) {
    $directory = Join-Path $Config.RuntimeDirectory 'pilot-ops-events'
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    return (Join-Path $directory ('target-pilot-' + (Get-Date -Format 'yyyyMMdd') + '.jsonl'))
}

function Add-TargetPilotOpsEvent($Config, [ValidateSet('READINESS','START','RECOVERY','COMPONENT_RECOVERY')] [string]$Action, [ValidateSet('READY','NOT_READY','STARTED','RECOVERED','FAILED')] [string]$Outcome, $Readiness = $null, [string[]]$Components = @()) {
    $event = [ordered]@{
        schemaVersion = 'target-pilot-ops-event.v1'
        recordedUtc = [DateTime]::UtcNow.ToString('o')
        action = $Action
        outcome = $Outcome
        components = @($Components | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    if ($null -ne $Readiness) {
        $event.state = [string]$Readiness.State
        $event.ready = [bool]$Readiness.Ready
        $event.serviceFailures = @($Readiness.ServiceFailures)
        $event.firewallState = if ($Readiness.Firewall) { [string]$Readiness.Firewall.State } else { '' }
        $event.probes = [ordered]@{
            tcpReachable = [bool]$Readiness.Probes.TcpReachable
            customerPage = [bool]$Readiness.Probes.CustomerPage.Reachable
            ragProxy = [bool]$Readiness.Probes.RagProxy.Reachable
            platformProxy = [bool]$Readiness.Probes.PlatformProxy.Reachable
        }
    }
    $event | ConvertTo-Json -Compress | Add-Content -LiteralPath (Get-TargetPilotOpsEventPath $Config) -Encoding UTF8
}

function Get-TargetPilotCustomerAccess($ServerHost, [int]$Port = 5173, [scriptblock]$HttpProbe = $null, [scriptblock]$TcpProbe = $null) {
    if (-not (Test-PrivateLanIpv4 ([string]$ServerHost))) {
        return [pscustomobject]@{ State='UNSAFE_SERVER_ADDRESS'; Ready=$false; ServerHost=[string]$ServerHost; Port=$Port; Probes=$null }
    }
    if ($Port -ne 5173) {
        return [pscustomobject]@{ State='UNSUPPORTED_CUSTOMER_PORT'; Ready=$false; ServerHost=[string]$ServerHost; Port=$Port; Probes=$null }
    }
    $baseUrl = "http://${ServerHost}:$Port/"
    $authority = "http://${ServerHost}:$Port"
    $tcpReachable = if ($TcpProbe) { [bool](& $TcpProbe $ServerHost $Port) } else { Test-TargetPilotTcpProbe $ServerHost $Port }
    $customerPage = if ($HttpProbe) { & $HttpProbe $baseUrl } else { Get-TargetPilotHttpProbe $baseUrl }
    $ragProxy = if ($HttpProbe) { & $HttpProbe "$authority/rag-api/api/health" } else { Get-TargetPilotHttpProbe "$authority/rag-api/api/health" }
    $platformProxy = if ($HttpProbe) { & $HttpProbe "$authority/platform-api/health" } else { Get-TargetPilotHttpProbe "$authority/platform-api/health" }
    $state = if (-not $tcpReachable) {
        'NETWORK_SEGMENTED'
    } elseif (-not $customerPage.Reachable -or -not $ragProxy.Reachable -or -not $platformProxy.Reachable) {
        'CUSTOMER_PATH_UNAVAILABLE'
    } else {
        'READY_FOR_CUSTOMER_ACCESS'
    }
    return [pscustomobject]@{
        State=$state
        Ready=($state -eq 'READY_FOR_CUSTOMER_ACCESS')
        ServerHost=[string]$ServerHost
        Port=$Port
        SimulationScope='Run this script on the second controlled customer computer; it does not read or save customer content.'
        Probes=[pscustomobject]@{ TcpReachable=$tcpReachable; CustomerPage=$customerPage; RagProxy=$ragProxy; PlatformProxy=$platformProxy }
    }
}

function Get-TargetPilotReadiness($Config, [ValidateSet('Lan','Local')] [string]$Mode = 'Lan', [object[]]$ServiceStatuses = $null, [scriptblock]$HttpProbe = $null, [scriptblock]$TcpProbe = $null, $FirewallReadiness = $null) {
    $customerUri = [uri]$Config.CustomerWebUrl
    $customerAuthority = $customerUri.GetLeftPart([System.UriPartial]::Authority)
    $customerHost = [string]$customerUri.Host
    $customerPort = [int]$customerUri.Port
    $adminUri = [uri]$Config.AdminWebUrl
    $loopbackHosts = @('127.0.0.1', '::1', 'localhost')
    $adminLoopback = -not [bool]$Config.AdminEnableLanMode -and
        [string]$Config.AdminWebBindAddress -in $loopbackHosts -and
        [string]$adminUri.Host -in $loopbackHosts

    $networkReady = $true
    if ($Mode -eq 'Lan') {
        $hasLanSelection = $Config.ContainsKey('LanSelection') -and $null -ne $Config.LanSelection
        $privateCustomerHost = Test-PrivateLanIpv4 $customerHost
        $bindMatchesCustomer = $Config.ContainsKey('CustomerWebBindAddress') -and [string]$Config.CustomerWebBindAddress -eq $customerHost
        $networkCategory = if ($Config.ContainsKey('LanNetworkProfile') -and $null -ne $Config.LanNetworkProfile) { [string]$Config.LanNetworkProfile.NetworkCategory } else { '' }
        $networkReady = $hasLanSelection -and $privateCustomerHost -and $bindMatchesCustomer -and $networkCategory -in @('Private', 'DomainAuthenticated')
    } else {
        $networkReady = $customerHost -in $loopbackHosts
    }

    $firewall = if ($Mode -eq 'Lan') {
        if ($null -ne $FirewallReadiness) { $FirewallReadiness } else { Get-TargetPilotFirewallReadiness $Config }
    } else {
        [pscustomobject]@{ State='NOT_APPLICABLE_LOCAL_MODE'; Ready=$true; ExpectedPort=0; ExpectedSubnet='' }
    }

    if ($null -eq $ServiceStatuses) { $ServiceStatuses = Get-TargetPilotServiceStatuses $Config }
    $serviceFailures = @($ServiceStatuses | Where-Object {
        $status = $_.Status
        $recordValid = $status.Record -and $status.Record.Valid
        $status.State -ne '运行中（RUNNING）' -or $status.HealthState -ne '可用' -or -not $recordValid
    })

    $tcpReachable = if ($TcpProbe) { [bool](& $TcpProbe $customerHost $customerPort) } else { Test-TargetPilotTcpProbe $customerHost $customerPort }
    $customerPage = if ($HttpProbe) { & $HttpProbe ([string]$Config.CustomerWebUrl) } else { Get-TargetPilotHttpProbe $Config.CustomerWebUrl }
    $ragProxy = if ($HttpProbe) { & $HttpProbe "$customerAuthority/rag-api/api/health" } else { Get-TargetPilotHttpProbe "$customerAuthority/rag-api/api/health" }
    $platformProxy = if ($HttpProbe) { & $HttpProbe "$customerAuthority/platform-api/health" } else { Get-TargetPilotHttpProbe "$customerAuthority/platform-api/health" }

    $state = if (-not $adminLoopback) {
        'ADMIN_LOOPBACK_REQUIRED'
    } elseif (-not $networkReady) {
        if ($Mode -eq 'Lan') { 'LAN_CONFIGURATION_REQUIRED' } else { 'LOCAL_CONFIGURATION_REQUIRED' }
    } elseif (-not $firewall.Ready) {
        'FIREWALL_CONFIGURATION_REQUIRED'
    } elseif ($serviceFailures.Count -gt 0) {
        'SERVICE_NOT_READY'
    } elseif (-not $tcpReachable) {
        'NETWORK_SEGMENTED'
    } elseif (-not $customerPage.Reachable -or -not $ragProxy.Reachable -or -not $platformProxy.Reachable) {
        'CUSTOMER_PATH_UNAVAILABLE'
    } else {
        'READY_FOR_CUSTOMER_PILOT'
    }

    return [pscustomobject]@{
        SchemaVersion = 'target-pilot-readiness.v1'
        CheckedUtc = [DateTime]::UtcNow.ToString('o')
        Mode = $Mode
        State = $state
        Ready = $state -eq 'READY_FOR_CUSTOMER_PILOT'
        SimulationScope = if ($Mode -eq 'Lan') { 'server-side LAN endpoint probe only; a second customer computer must still be accepted manually' } else { 'server-local endpoint probe only' }
        CustomerUrl = [string]$Config.CustomerWebUrl
        AdminUrl = [string]$Config.AdminWebUrl
        AdminLoopback = $adminLoopback
        NetworkReady = $networkReady
        Firewall = $firewall
        Services = $ServiceStatuses
        ServiceFailures = @($serviceFailures | ForEach-Object { $_.Label })
        Probes = [pscustomobject]@{ TcpReachable=$tcpReachable; CustomerPage=$customerPage; RagProxy=$ragProxy; PlatformProxy=$platformProxy }
    }
}

function Save-TargetPilotReadinessReport($Config, $Readiness) {
    $directory = Join-Path $Config.RuntimeDirectory 'pilot-readiness'
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $path = Join-Path $directory ("target-pilot-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    $safeServices = @($Readiness.Services | ForEach-Object {
        $status = $_.Status
        [ordered]@{ label=$_.Label; state=$status.State; port=$status.Port; portState=$status.PortState; healthState=$status.HealthState; managedPid=$status.ManagedProcessId; listenerPid=$status.ListenerProcessId; recordValid=[bool]($status.Record -and $status.Record.Valid) }
    })
    $safeReport = [ordered]@{
        schemaVersion = $Readiness.SchemaVersion
        checkedUtc = $Readiness.CheckedUtc
        mode = $Readiness.Mode
        state = $Readiness.State
        ready = [bool]$Readiness.Ready
        simulationScope = $Readiness.SimulationScope
        customerUrl = $Readiness.CustomerUrl
        adminUrl = $Readiness.AdminUrl
        adminLoopback = [bool]$Readiness.AdminLoopback
        networkReady = [bool]$Readiness.NetworkReady
        firewall = [ordered]@{ state=[string]$Readiness.Firewall.State; ready=[bool]$Readiness.Firewall.Ready; expectedPort=[int]$Readiness.Firewall.ExpectedPort; expectedSubnet=[string]$Readiness.Firewall.ExpectedSubnet }
        serviceFailures = @($Readiness.ServiceFailures)
        services = $safeServices
        probes = [ordered]@{
            tcpReachable = [bool]$Readiness.Probes.TcpReachable
            customerPage = [ordered]@{ reachable=[bool]$Readiness.Probes.CustomerPage.Reachable; statusCode=[int]$Readiness.Probes.CustomerPage.StatusCode }
            ragProxy = [ordered]@{ reachable=[bool]$Readiness.Probes.RagProxy.Reachable; statusCode=[int]$Readiness.Probes.RagProxy.StatusCode }
            platformProxy = [ordered]@{ reachable=[bool]$Readiness.Probes.PlatformProxy.Reachable; statusCode=[int]$Readiness.Probes.PlatformProxy.StatusCode }
        }
    }
    $safeReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Write-TargetPilotReadiness($Readiness, [string]$ReportPath = '') {
    Write-Host "试运行就绪状态：$($Readiness.State)" -ForegroundColor $(if ($Readiness.Ready) { 'Green' } else { 'Yellow' })
    foreach ($service in $Readiness.Services) {
        $status = $service.Status
        Write-Host "$($service.Label)：$($status.State)；受管 PID $($status.ManagedProcessId)；监听 PID $($status.ListenerProcessId)；health：$($status.HealthState)"
    }
    Write-Host "客服入口：$($Readiness.CustomerUrl)；TCP：$($Readiness.Probes.TcpReachable)；页面：$($Readiness.Probes.CustomerPage.Reachable)；/rag-api：$($Readiness.Probes.RagProxy.Reachable)；/platform-api：$($Readiness.Probes.PlatformProxy.Reachable)"
    Write-Host "运营后台：$($Readiness.AdminUrl)；仅本机：$($Readiness.AdminLoopback)"
    Write-Host "5173 防火墙 Gate：$($Readiness.Firewall.State)；就绪：$($Readiness.Firewall.Ready)"
    Write-Host "模拟范围：$($Readiness.SimulationScope)"
    if (-not [string]::IsNullOrWhiteSpace($ReportPath)) { Write-Host "已写入脱敏就绪报告：$ReportPath" }
    if (-not $Readiness.Ready) {
        switch ($Readiness.State) {
            'SERVICE_NOT_READY' { Write-Host "下一步：先运行 检查局域网客服状态.bat；仅在核对运行记录后使用 停止AI客服.bat，再重新启动。未通过服务：$($Readiness.ServiceFailures -join '、')" -ForegroundColor Yellow }
            'NETWORK_SEGMENTED' { Write-Host '下一步：核对 Private 网络、5173 专用防火墙规则和同网段设备；仍不可达时记录 NETWORK_SEGMENTED，不开放 8000/8011/5174。' -ForegroundColor Yellow }
            'CUSTOMER_PATH_UNAVAILABLE' { Write-Host '下一步：保留服务进程，检查 B 的 Vite 代理与 A/C health；不要在客服电脑直连 8000、8011 或 5174。' -ForegroundColor Yellow }
            'FIREWALL_CONFIGURATION_REQUIRED' { Write-Host '下一步：在受控 Private 网络上先运行检查AI客服防火墙.bat；如确认需要规则，使用现有配置AI客服防火墙.bat 显式创建仅限当前子网的 TCP 5173 入站规则。不要开放 8000、8011 或 5174。' -ForegroundColor Yellow }
            'ADMIN_LOOPBACK_REQUIRED' { Write-Host '下一步：将 AdminWebBindAddress 和 AdminWebUrl 恢复为 127.0.0.1，且保持 AdminEnableLanMode=false；本轮不开放 5174。' -ForegroundColor Yellow }
            default { Write-Host '下一步：检查 LAN 网卡选择和 Private 网络配置；脚本未修改防火墙、网络或未知进程。' -ForegroundColor Yellow }
        }
    }
}

function Assert-Dependencies($Config) {
    foreach ($item in @(@{Name='RAG Python';Path=$Config.RagPythonPath}, @{Name='平台 Python';Path=$Config.PlatformPythonPath})) { & $item.Path --version | Out-Null; if ($LASTEXITCODE -ne 0) { throw "$($item.Name) 无法执行：$($item.Path)" } }
    Get-AiCsInternalServiceToken $Config | Out-Null
    Assert-OllamaReady $Config | Out-Null
    foreach ($path in @((Join-Path $Config.RepositoryRoot 'backend\.venv\Scripts\python.exe'), (Join-Path $Config.RepositoryRoot 'platform_backend\.venv\Scripts\python.exe'))) { if (-not (Test-Path -LiteralPath $path)) { throw "缺少预先安装的运行依赖：$path" } }
    Assert-ProductionWebDependencies $Config 'frontend' | Out-Null
}

function Assert-RagVirtualEnvironment($Config) {
    $ragVenvPython = Join-Path $Config.RepositoryRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $ragVenvPython)) {
        throw "A .venv 缺失：$ragVenvPython。脚本不会自动安装依赖。"
    }
}

function Write-StartupFailureSummary($Config, [string[]]$StartedServices) {
    Write-Host '启动失败；本次启动流程服务状态：' -ForegroundColor Yellow
    foreach ($service in @(@{ Label='C'; Name='platform' }, @{ Label='A'; Name='rag' }, @{ Label='B'; Name='customer-web' }, @{ Label='Admin'; Name='admin-web' })) {
        $state = if ($StartedServices -contains $service.Name) { '已启动' } else { '未启动' }
        Write-Host "$($service.Label)：$state"
    }
}

function Stop-StartedServices($Config, [string[]]$StartedServices) {
    $cleanupFailures = @()
    foreach ($name in @('admin-web','customer-web','rag','platform')) {
        if ($StartedServices -notcontains $name) { continue }
        try {
            $record = $null
            $recordPath = Get-ServiceRecordPath $Config $name
            if (Test-Path -LiteralPath $recordPath) {
                $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if (-not ($record.PSObject.Properties.Name -contains 'listener_pid')) {
                    # A failure can occur after HTTP readiness but before the listener
                    # child was written to the record. Reuse the normal identity gate
                    # before stopping; never infer ownership from the port alone.
                    Update-ManagedServiceListenerRecord $Config $name | Out-Null
                }
            }
            Stop-ManagedService $Config $name
            $remainingRecord = Test-Path -LiteralPath $recordPath
            $remainingOwners = @()
            if ($null -ne $record -and $record.PSObject.Properties.Name -contains 'port') {
                $remainingOwners = @(Get-PortOwner ([int]$record.port))
            }
            if ($remainingRecord -or $remainingOwners.Count -gt 0) {
                throw "$name 自动清理后仍存在运行记录或监听进程。"
            }
        } catch {
            $cleanupFailures += $name
            Write-Warning "启动失败自动清理未能停止 $name：$($_.Exception.Message)。请使用状态脚本核对受管记录。"
        }
    }
    if ($cleanupFailures.Count -eq 0 -and $StartedServices.Count -gt 0) {
        Write-Host '启动失败自动清理完成：本轮已启动服务均已停止。' -ForegroundColor Yellow
    }
    return @($cleanupFailures)
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
    $check = $null
    foreach ($attempt in 1..2) {
        $check = Test-RecordedProcess $Config $Name
        if ($check.Valid -or (-not $check.Process -and -not $check.ListenerProcess) -or $attempt -eq 2) { break }
        # A bounded WMI query may transiently time out on Windows. Retry once;
        # never relax identity fields and never fall back to killing by port.
        Start-Sleep -Milliseconds 250
    }
    if (-not $check.Process -and -not $check.ListenerProcess) {
        $owners = @(Get-PortOwner ([int]$check.Record.port))
        if ($owners.Count -gt 0) { Write-Warning "$Name：记录的受管 PID 已退出，但端口仍由 PID $($owners -join ', ') 监听；拒绝清理记录或按端口停止。"; return }
        Remove-Item -LiteralPath $path -Force
        Write-Host "$Name：记录的进程已退出，端口未监听，已清理记录。"
        return
    }
    if (-not $check.Valid) { Write-Warning "$Name：拒绝停止 PID $($check.Process.Id)，原因：$($check.Reason)。请人工核对后处理。"; return }
    if ($check.ListenerProcess) {
        if ($check.Process) {
            $remaining = @(Stop-VerifiedProcessTree $check.Process.Id $check.ListenerProcess.Id)
        } else {
            Stop-Process -Id $check.ListenerProcess.Id -ErrorAction Stop
            Start-Sleep -Milliseconds 500
            $remaining = @(Get-Process -Id $check.ListenerProcess.Id -ErrorAction SilentlyContinue)
        }
        if ($remaining.Count -gt 0) { throw "$Name 的已验证进程树未能停止（PID $($remaining -join ', ')），请人工处理。" }
        $owners = @(Get-PortOwner ([int]$check.Record.port))
        if ($owners.Count -gt 0) { throw "$Name 的端口 $($check.Record.port) 仍由 PID $($owners -join ', ') 监听；不会按端口强杀。" }
    } else {
        Stop-Process -Id $check.Process.Id -ErrorAction Stop
        Start-Sleep -Milliseconds 500
        if (Get-Process -Id $check.Process.Id -ErrorAction SilentlyContinue) { throw "$Name（PID $($check.Process.Id)）未能停止，请人工处理。" }
    }
    Remove-Item -LiteralPath $path -Force
    $listenerDescription = if ($check.ListenerProcess) { "；监听 PID $($check.ListenerProcess.Id)" } else { '' }
    Write-Host "$Name 已停止（受管 PID $($check.Record.pid)$listenerDescription）。"
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
    # R016 protects browser-facing test-catalog management with OPERATOR/ADMIN
    # authentication. Startup must not bypass that boundary or depend on a user
    # credential, so it verifies the frozen loopback-only A export projection.
    $packageId = [uri]::EscapeDataString([string]$Config.TestKnowledgePackageId)
    try {
        $package = Get-Json (Get-ServiceUrl $Config $Config.PlatformPort "/api/v1/test-knowledge-packages/$packageId/rag-export") 'C internal knowledge package' (Get-AiCsInternalServiceHeaders $Config)
        if ([string]$package.package_id -ne [string]$Config.TestKnowledgePackageId) { return @() }
        $package | Add-Member -NotePropertyName import_status -NotePropertyValue 'INTERNAL_EXPORT_AVAILABLE' -Force
        return @($package)
    } catch {
        return @()
    }
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

function Get-TestKnowledgeSyncHistory($Config) {
    $recordPath = Get-TestKnowledgeSyncRecordPath $Config
    if (-not (Test-Path -LiteralPath $recordPath)) {
        return [pscustomobject]@{
            State = 'NO_HISTORY'
            PackageId = $null
            SyncedItems = $null
            CollectionCount = $null
            VerifiedUtc = $null
        }
    }

    try {
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return [pscustomobject]@{
            State = 'INVALID_HISTORY'
            PackageId = $null
            SyncedItems = $null
            CollectionCount = $null
            VerifiedUtc = $null
        }
    }

    if ([string]$record.packageId -ne [string]$Config.TestKnowledgePackageId) {
        return [pscustomobject]@{
            State = 'OTHER_PACKAGE_HISTORY'
            PackageId = [string]$record.packageId
            SyncedItems = $null
            CollectionCount = $null
            VerifiedUtc = $null
        }
    }

    return [pscustomobject]@{
        State = 'HISTORICAL_SYNC'
        PackageId = [string]$record.packageId
        SyncedItems = [int]$record.syncedItems
        CollectionCount = [int]$record.collectionCount
        VerifiedUtc = [string]$record.verifiedUtc
    }
}

function Get-RagKnowledgeRuntimeStatistics($Config) {
    $runtimeUrl = Get-ServiceUrl $Config $Config.RagPort '/api/knowledge/statistics'
    try {
        $response = Get-Json $runtimeUrl 'A 运行时知识统计' (Get-AiCsInternalServiceHeaders $Config)
        $data = if ($null -ne $response.data) { $response.data } else { $response }
        $activeCollectionName = if ($data.PSObject.Properties.Name -contains 'active_collection_name') { [string]$data.active_collection_name } else { [string]$data.collection_name }
        $activeCollectionChunkCount = if ($data.PSObject.Properties.Name -contains 'active_collection_chunk_count' -and $null -ne $data.active_collection_chunk_count) { [int]$data.active_collection_chunk_count } else { [int]$data.chunk_count }
        $activeCollectionAvailable = if ($data.PSObject.Properties.Name -contains 'active_collection_available') { [bool]$data.active_collection_available } else { -not [string]::IsNullOrWhiteSpace($activeCollectionName) }
        $availableCollections = if ($data.PSObject.Properties.Name -contains 'available_collections') { @($data.available_collections) } else { @([pscustomobject]@{ name=$activeCollectionName; chunk_count=$activeCollectionChunkCount }) }
        return [pscustomobject]@{
            State = 'AVAILABLE'
            RuntimeUrl = $runtimeUrl
            DocumentCount = [int]$data.document_count
            ChunkCount = [int]$data.chunk_count
            CollectionName = $activeCollectionName
            ActiveCollectionName = $activeCollectionName
            ActiveCollectionChunkCount = $activeCollectionChunkCount
            ActiveCollectionAvailable = $activeCollectionAvailable
            AvailableCollections = $availableCollections
            VectorDatabase = [string]$data.vector_database
            Error = $null
        }
    } catch {
        return [pscustomobject]@{
            State = 'UNAVAILABLE'
            RuntimeUrl = $runtimeUrl
            DocumentCount = $null
            ChunkCount = $null
            CollectionName = $null
            ActiveCollectionName = $null
            ActiveCollectionChunkCount = $null
            ActiveCollectionAvailable = $false
            AvailableCollections = @()
            VectorDatabase = $null
            Error = $_.Exception.Message
        }
    }
}

function Get-TestKnowledgeRuntimeConsistency($SyncHistory, $RuntimeStatistics, [string]$ExpectedCollectionName = '') {
    if ($RuntimeStatistics.State -ne 'AVAILABLE') { return 'STATISTICS_UNAVAILABLE' }
    if ($SyncHistory.State -ne 'HISTORICAL_SYNC') { return 'NO_HISTORICAL_COMPARISON' }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedCollectionName) -and $RuntimeStatistics.ActiveCollectionName -ne $ExpectedCollectionName) { return 'ACTIVE_COLLECTION_MISMATCH' }
    if ($RuntimeStatistics.ActiveCollectionChunkCount -ne $SyncHistory.CollectionCount) { return 'MISMATCH' }
    return 'MATCH'
}

function Format-RagAvailableCollections($RuntimeStatistics) {
    $items = @($RuntimeStatistics.AvailableCollections | ForEach-Object { "$([string]$_.name)=$([int]$_.chunk_count)" })
    if ($items.Count -eq 0) { return '无' }
    return ($items -join '，')
}

function Get-RagActiveCollectionStartupState($Config) {
    $statistics = Get-RagKnowledgeRuntimeStatistics $Config
    if ($statistics.State -ne 'AVAILABLE') {
        Write-Warning "A 知识统计不可用：$($statistics.Error)。A/C/B/Admin继续启动，但AI知识smoke将跳过。"
        return [pscustomobject]@{ Ready=$false; Statistics=$statistics; Reason='STATISTICS_UNAVAILABLE' }
    }
    if ($statistics.ActiveCollectionName -ne [string]$Config.RagActiveCollectionName) {
        Write-Warning "A active collection与配置不一致：配置=$($Config.RagActiveCollectionName)，运行=$($statistics.ActiveCollectionName)。服务继续启动，但AI知识smoke将跳过。"
        return [pscustomobject]@{ Ready=$false; Statistics=$statistics; Reason='ACTIVE_COLLECTION_MISMATCH' }
    }
    if (-not $statistics.ActiveCollectionAvailable -or [int]$statistics.ActiveCollectionChunkCount -le 0) {
        Write-Warning "A active collection无可用知识：$($statistics.ActiveCollectionName)=$($statistics.ActiveCollectionChunkCount) chunks；available=$(Format-RagAvailableCollections $statistics)。服务继续启动，但AI知识smoke将跳过。"
        return [pscustomobject]@{ Ready=$false; Statistics=$statistics; Reason='ACTIVE_COLLECTION_EMPTY' }
    }
    Write-Host "A active collection检查通过：$($statistics.ActiveCollectionName)=$($statistics.ActiveCollectionChunkCount) chunks；available=$(Format-RagAvailableCollections $statistics)。"
    return [pscustomobject]@{ Ready=$true; Statistics=$statistics; Reason='READY' }
}

function Sync-TestKnowledge($Config) {
    if (-not [bool]$Config.AutoSyncTestKnowledge) { Write-Host 'AutoSyncTestKnowledge=false，跳过 A 测试知识同步。'; return $null }
    $response = Invoke-RestMethod -UseBasicParsing -Method Post -Headers (Get-AiCsInternalServiceHeaders $Config) -Uri (Get-ServiceUrl $Config $Config.RagPort "/api/test-knowledge/sync/$($Config.TestKnowledgePackageId)") -TimeoutSec 120
    $data = if ($response.data) { $response.data } else { $response }
    if ([int]$data.synced_items -ne 47 -or [int]$data.collection_count -ne 47) { throw "A 测试知识同步数量异常：synced_items=$($data.synced_items)，collection_count=$($data.collection_count)，期望均为 47。" }
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory | Out-Null
    [ordered]@{ packageId=$Config.TestKnowledgePackageId; syncedItems=[int]$data.synced_items; collectionCount=[int]$data.collection_count; verifiedUtc=[datetime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Get-TestKnowledgeSyncRecordPath $Config) -Encoding UTF8
    Write-Host 'A 测试知识同步完成：47 条。'
    return $data
}

function Assert-RagRuntimeReady($Config) {
    $status = Get-Json (Get-ServiceUrl $Config $Config.RagPort '/api/status') 'A 状态' (Get-AiCsInternalServiceHeaders $Config)
    if (-not [bool]$status.ready -or -not [bool]$status.model_configured -or $null -ne $status.initialization_error) {
        throw "A 状态校验失败：ready=$($status.ready)，model_configured=$($status.model_configured)，initialization_error=$($status.initialization_error)。不会启动 B。"
    }
    return $status
}

function Wait-RagRuntimeReady($Config, [int]$Seconds) {
    $lastStatus = $null
    for ($i = 0; $i -lt $Seconds; $i++) {
        try {
            $lastStatus = Get-Json (Get-ServiceUrl $Config $Config.RagPort '/api/status') 'A 状态' (Get-AiCsInternalServiceHeaders $Config)
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
    # The active collection may coexist with newly imported C products that
    # have not yet been published. Use the configured package export as the
    # smoke context so an unrelated unpublished product cannot fail startup.
    $packageId = [uri]::EscapeDataString([string]$Config.TestKnowledgePackageId)
    $package = Get-Json (Get-ServiceUrl $Config $Config.PlatformPort "/api/v1/test-knowledge-packages/$packageId/rag-export") 'C active knowledge package' (Get-AiCsInternalServiceHeaders $Config)
    $productItem = @($package.items | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.product_id) } | Select-Object -First 1)[0]
    if ($null -eq $productItem) { throw 'C active knowledge package 没有可供聊天 smoke 使用的商品。' }
    $skuItem = @($package.items | Where-Object { [string]$_.product_id -eq [string]$productItem.product_id -and -not [string]::IsNullOrWhiteSpace([string]$_.sku_id) } | Select-Object -First 1)[0]
    $payload = @{ question='请根据当前商品资料介绍适用年龄和安全注意事项。'; context=@{ tenant_id=[string]$package.tenant_id; platform=[string]$package.platform; store_code=[string]$package.store_code; product_id=[string]$productItem.product_id; sku_id=if ($skuItem) { [string]$skuItem.sku_id } else { $null } } } | ConvertTo-Json -Depth 5
    try { $response = Invoke-RestMethod -UseBasicParsing -Method Post -Headers (Get-AiCsInternalServiceHeaders $Config) -ContentType 'application/json; charset=utf-8' -Body $payload -Uri (Get-ServiceUrl $Config $Config.RagPort '/api/chat') -TimeoutSec 120 } catch { throw "A 真实聊天 smoke 失败：$($_.Exception.Message)" }
    $data = if ($response.data) { $response.data } else { $response }
    $answer = [string]$data.answer
    if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '大模型尚未配置|大模型请求失败|NO_SCOPED_KNOWLEDGE' -or @($data.sources).Count -eq 0) { throw "A 真实聊天 smoke 未得到可用 Ollama 回答：$answer" }
    Write-Host 'A 真实 Ollama chat smoke 通过。'
    return $data
}
