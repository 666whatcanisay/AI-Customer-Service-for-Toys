[CmdletBinding()]
param(
    [int]$Port = 18443,
    [string]$BindAddress = '192.168.1.11',
    [int]$DiscoveryPort = 18421
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$runtimeRoot = Join-Path $repoRoot '.runtime\channel-agent-lan-host'
$logRoot = Join-Path $runtimeRoot 'logs'
$candidatePath = Join-Path $runtimeRoot 'lan-candidate-v13.json'
$certificate = Join-Path $runtimeRoot 'tls\channel-agent-host-v2.pem'
$privateKey = Join-Path $runtimeRoot 'tls\channel-agent-host-key.encrypted.pem'
$privateKeyCredentialReference = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/TLSKeyPassword'
$serviceCredentialReference = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/AI-CSService'
$pairingCredentialReference = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/PairingCodeV2'
$scheme = 'https'
$publicUrl = "${scheme}://${BindAddress}:$Port"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'CHANNEL_ENGINE_PYTHON_UNAVAILABLE'
}
if (-not (Test-Path -LiteralPath $certificate -PathType Leaf)) {
    throw 'HOST_CONTROL_CERTIFICATE_UNAVAILABLE'
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "PORT_${Port}_ALREADY_IN_USE"
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$pairingCode = (& $python -c 'from channel_agent.control_v2 import generate_pairing_code; print(generate_pairing_code())').Trim()
if ($pairingCode -notmatch '^[0-9A-HJ-NP-TV-Z]{12}$') {
    throw 'PAIRING_CODE_GENERATION_FAILED'
}
$pairingCode | & $python (Join-Path $repoRoot 'scripts\support\provision_channel_agent_pairing_credential.py') `
    --credential-reference $pairingCredentialReference --expires-in-seconds 300 | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'PAIRING_CREDENTIAL_PROVISIONING_FAILED' }

$env:PYTHONPATH = Join-Path $repoRoot 'src'
$env:CHANNEL_ENGINE_DATABASE_URL = 'sqlite:///' + ((Join-Path $repoRoot '.runtime\channel-engine.sqlite3').Replace('\','/'))
$env:CHANNEL_ENGINE_AGENT_CONTROL_V2_ENABLED = 'true'
$env:CHANNEL_ENGINE_AGENT_HOST_ID = 'ai-cs-desktop-0345200'
$env:CHANNEL_ENGINE_AGENT_PUBLIC_URL = $publicUrl
$env:CHANNEL_ENGINE_AGENT_PAIRING_CREDENTIAL_REFERENCE = $pairingCredentialReference
Remove-Item Env:\CHANNEL_ENGINE_AGENT_PAIRING_CODE -ErrorAction SilentlyContinue
$env:CHANNEL_ENGINE_AGENT_CA_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_DEVICE_CREDENTIAL_INDEX = Join-Path $runtimeRoot 'device-credential-index.json'
$env:CHANNEL_ENGINE_AGENT_ENVIRONMENT = 'STAGING'
$env:CHANNEL_ENGINE_TLS_CERTIFICATE = $certificate
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY = $privateKey
$env:CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE = $privateKeyCredentialReference
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CONTROL_ENABLED = 'true'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_ID = 'ai-cs-platform'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_KEY_ID = 'service-key-v1'
$env:CHANNEL_ENGINE_AI_CS_SERVICE_CREDENTIAL_REFERENCE = $serviceCredentialReference

$process = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_engine_production_host.py'),
    '--host', $BindAddress, '--port', [string]$Port
) -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'engine.stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'engine.stderr.log') `
    -PassThru

$ready = $false
foreach ($attempt in 1..40) {
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],verify=False,timeout=2,trust_env=False); raise SystemExit(0 if r.status_code == 200 and r.json().get('status') == 'healthy' else 1)" "$publicUrl/health" 2>$null
    $healthExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($healthExitCode -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "HOST_CONTROL_NOT_READY:$(Join-Path $logRoot 'engine.stderr.log')"
}

# Pairing discovery carries only public host identity and certificate material.
# The one-time code remains process-local and is placed on the administrator's
# clipboard for an explicit paste-and-confirm action in ChannelAgent.
[string]$certificatePem = [System.IO.File]::ReadAllText(
    $certificate,
    [System.Text.Encoding]::ASCII
)
$fingerprint = (Get-FileHash -LiteralPath $certificate -Algorithm SHA256).Hash.ToLowerInvariant()
$candidate = [ordered]@{
    control_protocol_version = '2.1'
    host_id = 'ai-cs-desktop-0345200'
    host_name = $env:COMPUTERNAME
    environment = 'STAGING'
    server_url = $publicUrl
    server_version = '0.2.0rc1'
    certificate_sha256 = $fingerprint
    ca_certificate_pem = $certificatePem
}
[System.IO.File]::WriteAllText(
    $candidatePath,
    ($candidate | ConvertTo-Json -Depth 4 -Compress),
    [System.Text.UTF8Encoding]::new($false)
)

$discovery = Start-Process -FilePath $python -ArgumentList @(
    (Join-Path $repoRoot 'scripts\run_channel_agent_lan_discovery.py'),
    '--candidate', $candidatePath, '--port', [string]$DiscoveryPort
) -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'discovery-v13.stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'discovery-v13.stderr.log') `
    -PassThru
Start-Sleep -Seconds 1
if (-not (Get-NetUDPEndpoint -LocalPort $DiscoveryPort -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $discovery.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw 'HOST_DISCOVERY_NOT_READY'
}
Set-Clipboard -Value $pairingCode

[pscustomobject]@{
    pid = $process.Id
    discovery_pid = $discovery.Id
    public_url = $publicUrl
    protocol = '2.1'
    pairing_code_delivery = 'WINDOWS_CLIPBOARD'
    pairing_code_expires_in_minutes = 5
} | ConvertTo-Json -Compress
