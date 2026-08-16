[CmdletBinding()]
param(
    [string]$AiCsRoot,
    [string]$BindAddress,
    [int]$AgentPort = 18443,
    [int]$OperationsPort = 18020,
    [int]$DiscoveryPort = 18421,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $PSScriptRoot 'Resolve-AiCsRepositoryRoot.ps1')
$AiCsRoot = Resolve-AiCsRepositoryRoot $repoRoot $AiCsRoot
if (-not (Test-Path -LiteralPath (Join-Path $AiCsRoot 'scripts\windows\start_lan_ai_customer_service.ps1') -PathType Leaf)) {
    throw "未找到 AI-CS 主机目录：$AiCsRoot"
}
$aiCsCommon = Join-Path $AiCsRoot 'scripts\windows\common_ai_customer_service.ps1'
. $aiCsCommon
$aiCsConfigPath = Resolve-AiCustomerServiceConfigPath $null
$aiCsLanConfig = Resolve-LanRuntimeConfig (Get-LocalConfig $aiCsConfigPath)
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键“启动局域网AI客服主机.bat”，选择“以管理员身份运行”。'
}
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Channel Engine Python 环境不可用。' }
$env:PYTHONPATH = Join-Path $repoRoot 'src'
if (-not $BindAddress) {
    $candidates = @(Get-NetIPConfiguration | Where-Object {
        $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' -and
        $_.NetAdapter.HardwareInterface -and $_.IPv4Address.IPAddress -notlike '169.254.*'
    })
    if ($candidates.Count -ne 1) { throw '无法唯一确定局域网网卡，请使用 -BindAddress 明确指定主机 IPv4。' }
    $BindAddress = [string]$candidates[0].IPv4Address.IPAddress
}
$ip = $null
if (-not [System.Net.IPAddress]::TryParse($BindAddress, [ref]$ip) -or $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'BindAddress 必须是有效 IPv4。'
}
$runtimeRoot = Join-Path $repoRoot '.runtime\channel-agent-lan-host'
$tlsRoot = Join-Path $runtimeRoot 'tls'
$logRoot = Join-Path $runtimeRoot 'logs'
$statePath = Join-Path $runtimeRoot 'host-state.json'
$candidatePath = Join-Path $runtimeRoot 'lan-candidate.json'
$hostId = 'ai-cs-' + (($env:COMPUTERNAME -replace '[^A-Za-z0-9._-]', '-').ToLowerInvariant())
$aiCsServiceId = 'ai-cs-platform'
$aiCsServiceKeyId = 'service-key-v1'
$aiCsServiceCredentialReference = "wincred://AI-CS/ChannelEngine/$hostId/AI-CSService"
$certificate = Join-Path $tlsRoot 'channel-agent-host-v2.pem'
$privateKey = Join-Path $tlsRoot 'channel-agent-host-key.encrypted.pem'
$opensslConfig = Join-Path $tlsRoot 'openssl.cnf'
$tlsCredentialReference = "wincred://AI-CS/ChannelEngine/$hostId/TLSKeyPassword"
New-Item -ItemType Directory -Path $tlsRoot, $logRoot -Force | Out-Null

@"
[req]
prompt = no
distinguished_name = dn
x509_extensions = v3
[dn]
CN = $BindAddress
[v3]
subjectAltName = IP:$BindAddress,DNS:$env:COMPUTERNAME
basicConstraints = critical,CA:TRUE
keyUsage = critical,digitalSignature,keyEncipherment,keyCertSign
extendedKeyUsage = serverAuth
"@ | Set-Content -LiteralPath $opensslConfig -Encoding ascii

if (-not (Test-Path -LiteralPath $certificate -PathType Leaf) -or -not (Test-Path -LiteralPath $privateKey -PathType Leaf)) {
    & $python (Join-Path $repoRoot 'scripts\support\provision_channel_agent_tls.py') `
        --certificate $certificate --private-key $privateKey `
        --openssl-config $opensslConfig --credential-reference $tlsCredentialReference
    if ($LASTEXITCODE -ne 0) { throw '加密 TLS 身份创建失败。' }
}

& $python (Join-Path $repoRoot 'scripts\support\provision_channel_agent_service_credential.py') `
    --credential-reference $aiCsServiceCredentialReference | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'AI-CS 主机接入凭据创建失败。凭据不会写入配置文件或日志。' }

$pairingCode = (& $python -c "from channel_agent.control_v2 import generate_pairing_code; print(generate_pairing_code())" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $pairingCode -notmatch '^[0-9A-HJ-NP-TV-Z]{12}$') { throw '无法生成一次性连接码。' }
$pairingCredentialReference = "wincred://AI-CS/ChannelEngine/$hostId/PairingCodeV2"
$pairingCode | & $python (Join-Path $repoRoot 'scripts\support\provision_channel_agent_pairing_credential.py') `
    --credential-reference $pairingCredentialReference --expires-in-seconds 300 | Out-Null
if ($LASTEXITCODE -ne 0) { throw '无法安全保存短期连接码。' }
$publicUrl = "https://${BindAddress}:$AgentPort"
$engineDatabasePath = Join-Path $runtimeRoot 'channel-engine.sqlite3'
$env:CHANNEL_ENGINE_DATABASE_URL = 'sqlite:///' + ($engineDatabasePath.Replace('\','/'))
$env:CHANNEL_ENGINE_DATABASE_BINDING_PATH = "$engineDatabasePath.binding.json"
$env:CHANNEL_ENGINE_DATABASE_ENVIRONMENT_ID = 'RC5_LAN_HOST'
$env:CHANNEL_ENGINE_REQUIRE_DATABASE_IDENTITY = 'true'
$env:CHANNEL_ENGINE_AGENT_CONTROL_V2_ENABLED = 'true'
$env:CHANNEL_ENGINE_AGENT_HOST_ID = $hostId
$env:CHANNEL_ENGINE_AGENT_PUBLIC_URL = $publicUrl
$env:CHANNEL_ENGINE_AGENT_PAIRING_CREDENTIAL_REFERENCE = $pairingCredentialReference
Remove-Item Env:\CHANNEL_ENGINE_AGENT_PAIRING_CODE -ErrorAction SilentlyContinue
$env:CHANNEL_ENGINE_AGENT_CA_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_DEVICE_CREDENTIAL_INDEX = Join-Path $runtimeRoot 'device-credential-index.json'
$env:CHANNEL_ENGINE_AGENT_ENVIRONMENT = 'STAGING'
$env:CHANNEL_ENGINE_TLS_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY = $privateKey
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE = $tlsCredentialReference
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CONTROL_ENABLED = 'true'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_ID = $aiCsServiceId
$env:CHANNEL_ENGINE_AI_CS_SERVICE_KEY_ID = $aiCsServiceKeyId
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CREDENTIAL_REFERENCE = $aiCsServiceCredentialReference

# The AI-CS launcher inherits references only. Both processes resolve the same
# opaque material from Windows Credential Manager; no secret crosses argv or disk.
$env:CHANNEL_AGENT_INTEGRATION_ENABLED = 'true'
$env:CHANNEL_AGENT_SERVER_URL = $publicUrl
$env:CHANNEL_AGENT_SERVICE_ID = $aiCsServiceId
$env:CHANNEL_AGENT_SERVICE_KEY_ID = $aiCsServiceKeyId
$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = $aiCsServiceCredentialReference
$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE = $certificate
$env:CHANNEL_ENGINE_OPERATIONS_DATABASE_URL = 'sqlite:///' + ((Join-Path $runtimeRoot 'operations-console.sqlite3').Replace('\','/'))
$env:CHANNEL_ENGINE_AI_CS_ADMIN_URL = "http://127.0.0.1:$($aiCsLanConfig.PlatformPort)"

$existing = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try { $existing = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $existing = $null }
}
if ($existing -and (Get-Process -Id ([int]$existing.engine_pid) -ErrorAction SilentlyContinue)) {
    throw 'Channel Agent 局域网主机已在运行，请先执行状态检查。'
}

$operationsListener = Get-NetTCPConnection -State Listen -LocalPort $OperationsPort -ErrorAction SilentlyContinue | Select-Object -First 1
if ($operationsListener) {
    $operationsProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($operationsListener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = if ($operationsProcess) { [string]$operationsProcess.CommandLine } else { '' }
    if ($commandLine -match 'channel_engine\.app:app') {
        Write-Host '检测到旧版18020开发控制台，正在受控停止并切换到正式运营控制台。' -ForegroundColor Yellow
        Stop-Process -Id ([int]$operationsListener.OwningProcess) -Force
        Start-Sleep -Milliseconds 500
    } else {
        throw "端口 $OperationsPort 已被其他程序占用。为避免误停未知程序，正式运营控制台未启动。"
    }
}

$firewallRules = @(
    @{ Name = 'AI-CS-ChannelAgent-Control-V2'; Protocol = 'TCP'; Port = $AgentPort },
    @{ Name = 'AI-CS-ChannelAgent-Discovery-V2'; Protocol = 'UDP'; Port = $DiscoveryPort },
    @{ Name = 'AI-CS-Customer-Web-LAN'; Protocol = 'TCP'; Port = [int]$aiCsLanConfig.CustomerWebPort }
)
foreach ($rule in $firewallRules) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow `
            -Profile Private -RemoteAddress LocalSubnet -Protocol $rule.Protocol `
            -LocalPort $rule.Port | Out-Null
    }
}

$aiCsStart = Join-Path $AiCsRoot 'scripts\windows\start_lan_ai_customer_service.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $aiCsStart -NoBrowser
if ($LASTEXITCODE -ne 0) { throw 'AI-CS 局域网服务启动失败，Channel Agent 主机未启动。' }

$engineOut = Join-Path $logRoot 'engine.stdout.log'
$engineErr = Join-Path $logRoot 'engine.stderr.log'
$engine = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_production_host.py'),
    '--host','0.0.0.0','--port',[string]$AgentPort
) -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $engineOut -RedirectStandardError $engineErr -PassThru

$pem = Get-Content -LiteralPath $certificate -Raw -Encoding ascii
$fingerprint = (Get-FileHash -LiteralPath $certificate -Algorithm SHA256).Hash.ToLowerInvariant()
$customerWebCertificate = [string]$aiCsLanConfig.CustomerWebTlsCertificateReference
if (-not (Test-Path -LiteralPath $customerWebCertificate -PathType Leaf)) {
    throw 'AI-CS 客服页面 TLS 证书不可用。'
}
$customerWebPem = Get-Content -LiteralPath $customerWebCertificate -Raw -Encoding ascii
$customerWebFingerprint = (Get-FileHash -LiteralPath $customerWebCertificate -Algorithm SHA256).Hash.ToLowerInvariant()
$candidateJson = [ordered]@{
    control_protocol_version = '2.1'
    host_id = $hostId
    host_name = $env:COMPUTERNAME
    environment = 'STAGING'
    server_url = $publicUrl
    server_version = '0.2.0rc1'
    certificate_sha256 = $fingerprint
    ca_certificate_pem = $pem
    customer_service_url = [string]$aiCsLanConfig.CustomerWebUrl
    customer_service_certificate_sha256 = $customerWebFingerprint
    customer_service_ca_certificate_pem = $customerWebPem
} | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($candidatePath, $candidateJson, [System.Text.UTF8Encoding]::new($false))

$discoveryOut = Join-Path $logRoot 'discovery.stdout.log'
$discoveryErr = Join-Path $logRoot 'discovery.stderr.log'
$discovery = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_agent_lan_discovery.py'),
    '--candidate',$candidatePath,'--port',[string]$DiscoveryPort
) -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $discoveryOut -RedirectStandardError $discoveryErr -PassThru

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],verify=False,timeout=2,trust_env=False); raise SystemExit(0 if r.status_code==200 else 1)" "$publicUrl/health" 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) {
    Stop-Process -Id $discovery.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
    throw "Channel Engine 未就绪，请查看 $engineErr"
}


& $python (Join-Path $repoRoot 'scripts\support\verify_channel_agent_service_link.py') `
    --server-url $publicUrl --ca-certificate $certificate `
    --service-id $aiCsServiceId --key-id $aiCsServiceKeyId `
    --credential-reference $aiCsServiceCredentialReference
if ($LASTEXITCODE -ne 0) {
    Stop-Process -Id $discovery.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
    throw 'AI-CS 到18443的签名设备查询未通过；18020不会回退到Mock或本地设备库。'
}

$operationsOut = Join-Path $logRoot 'operations.stdout.log'
$operationsErr = Join-Path $logRoot 'operations.stderr.log'
$operations = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_operations_console.py'),
    '--host','127.0.0.1','--port',[string]$OperationsPort
) -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $operationsOut -RedirectStandardError $operationsErr -PassThru

$operationsUrl = "http://127.0.0.1:$OperationsPort"
$operationsReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],timeout=2,trust_env=False); raise SystemExit(0 if r.status_code==200 else 1)" "$operationsUrl/health" 2>$null
        if ($LASTEXITCODE -eq 0) { $operationsReady = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $operationsReady) {
    Stop-Process -Id $operations.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $discovery.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
    throw "正式运营控制台未就绪，请查看 $operationsErr"
}
[ordered]@{
    schema_version = 'channel-agent-lan-host.v2'
    status = 'READY'
    host_id = $hostId
    bind_address = $BindAddress
    public_url = $publicUrl
    operations_url = "$operationsUrl/ops/console#devices"
    engine_pid = $engine.Id
    discovery_pid = $discovery.Id
    operations_pid = $operations.Id
    started_at = [DateTimeOffset]::UtcNow.ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host 'AI-CS + Channel Engine 局域网主机已就绪。' -ForegroundColor Green
Write-Host "主机：$env:COMPUTERNAME ($BindAddress)"
Write-Host "一次性连接码：$($pairingCode.Substring(0,4))-$($pairingCode.Substring(4,4))-$($pairingCode.Substring(8,4))" -ForegroundColor Yellow
Write-Host '请在客服电脑核对主机信息、输入连接码并人工确认。连接码 5 分钟后失效且只能使用一次。'
Write-Host "运营控制台：$operationsUrl/ops/console#devices（设备状态权威来源：18443）"
Write-Host "运行状态：$statePath"
if (-not $NoBrowser) { Start-Process "$operationsUrl/ops/console#devices" }
