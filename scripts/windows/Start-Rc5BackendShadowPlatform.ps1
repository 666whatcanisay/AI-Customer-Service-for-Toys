[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AiCsRoot,
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [string]$HostControlUrl = 'https://127.0.0.1:19443',
    [int]$Port = 8522
)

$ErrorActionPreference = 'Stop'
$aiCsRoot = [IO.Path]::GetFullPath($AiCsRoot)
$databasePath = [IO.Path]::GetFullPath($DatabasePath)
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
$configPath = Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\ux-acceptance.local.ps1'
$common = Join-Path $aiCsRoot 'scripts\windows\common_ai_customer_service.ps1'
$engineRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$engineRuntime = Join-Path $engineRoot '.runtime\channel-agent-lan-host'

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "PORT_${Port}_ALREADY_IN_USE"
}
foreach ($required in @($common, $configPath, $databasePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "RC5_SHADOW_PLATFORM_DEPENDENCY_MISSING:$required"
    }
}

. $common
$config = Get-LocalConfig $configPath
$config.PlatformDatabaseUrl = 'sqlite:///' + $databasePath.Replace('\', '/')
$config.PlatformPort = $Port
$config.CorsAllowedOrigins = @("http://127.0.0.1:$Port", "http://localhost:$Port")
$config.PlatformKnowledgeMaterialStorageDirectory = Join-Path $evidenceRoot 'knowledge-materials'
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
New-Item -ItemType Directory -Path $config.PlatformKnowledgeMaterialStorageDirectory -Force | Out-Null

$env:CHANNEL_AGENT_INTEGRATION_ENABLED = 'true'
$env:CHANNEL_AGENT_SERVER_URL = $HostControlUrl.TrimEnd('/')
$env:CHANNEL_AGENT_SERVICE_ID = 'ai-cs-platform'
$env:CHANNEL_AGENT_SERVICE_KEY_ID = 'service-key-v1'
$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = 'wincred://AI-CS/ChannelEngine/ai-cs-desktop-0345200/AI-CSService'
$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE = Join-Path $engineRuntime 'tls\channel-agent-host-v2.pem'
$runtimeEnvironment = Get-LocalPlatformEnvironment $config

Invoke-WithProcessEnvironment $runtimeEnvironment {
    Invoke-PlatformMigration $config
} | Out-Null

$platform = Invoke-WithProcessEnvironment $runtimeEnvironment {
    Start-Process -FilePath $config.PlatformPythonPath -ArgumentList @(
        '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
        '--port', [string]$Port, '--no-access-log'
    ) -WorkingDirectory (Join-Path $aiCsRoot 'platform_backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $evidenceRoot 'platform.stdout.log') `
        -RedirectStandardError (Join-Path $evidenceRoot 'platform.stderr.log') `
        -PassThru
}

$ready = $false
foreach ($attempt in 1..80) {
    try {
        $health = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch {
        Start-Sleep -Milliseconds 250
    }
}
if (-not $ready) {
    Stop-Process -Id $platform.Id -Force -ErrorAction SilentlyContinue
    throw "RC5_SHADOW_PLATFORM_NOT_READY:$(Join-Path $evidenceRoot 'platform.stderr.log')"
}

$owner = Get-NetTCPConnection -State Listen -LocalPort $Port | Select-Object -First 1
[pscustomobject]@{
    platform_pid = $owner.OwningProcess
    launcher_pid = $platform.Id
    database_path = $databasePath
    host_control_url = $env:CHANNEL_AGENT_SERVER_URL
    ai_service_base_url = $runtimeEnvironment.AI_SERVICE_BASE_URL
    real_send_enabled = $false
} | ConvertTo-Json -Depth 3 -Compress
