[CmdletBinding()]
param(
    [string]$AiCsRoot,
    [int]$Port = 18442
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $AiCsRoot) {
    $AiCsRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '..\AI-CS'))
}

$common = Join-Path $AiCsRoot 'scripts\windows\common_ai_customer_service.ps1'
$configPath = Join-Path $AiCsRoot '.runtime\r027-ux-acceptance-data-v1\ux-acceptance.local.ps1'
if (-not (Test-Path -LiteralPath $common -PathType Leaf)) { throw 'AI_CS_COMMON_SCRIPT_MISSING' }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'AI_CS_RUNTIME_CONFIG_MISSING' }
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "SHADOW_PORT_${Port}_IN_USE"
}

. $common
$config = Get-LocalConfig $configPath
$hostId = 'ai-cs-' + (($env:COMPUTERNAME -replace '[^A-Za-z0-9._-]', '-').ToLowerInvariant())
$env:CHANNEL_AGENT_INTEGRATION_ENABLED = 'true'
$env:CHANNEL_AGENT_SERVER_URL = 'https://192.168.1.11:18443'
$env:CHANNEL_AGENT_SERVICE_ID = 'ai-cs-platform'
$env:CHANNEL_AGENT_SERVICE_KEY_ID = 'service-key-v1'
$env:CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE = "wincred://AI-CS/ChannelEngine/$hostId/AI-CSService"
$env:CHANNEL_AGENT_CA_CERTIFICATE_FILE = Join-Path $repoRoot '.runtime\channel-agent-lan-host\tls\channel-agent-host-v2.pem'
$runtimeEnvironment = Get-LocalPlatformEnvironment $config
$logDirectory = Join-Path $config.RuntimeDirectory 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

$process = $null
try {
    $process = Invoke-WithProcessEnvironment -Environment $runtimeEnvironment -Action {
        Start-Process -FilePath $config.PlatformPythonPath -ArgumentList @(
            '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
            '--port', [string]$Port, '--no-access-log'
        ) -WorkingDirectory (Join-Path $AiCsRoot 'platform_backend') -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDirectory 'platform-enrollment-shadow.out.log') `
            -RedirectStandardError (Join-Path $logDirectory 'platform-enrollment-shadow.err.log') `
            -PassThru
    }

    $ready = $false
    foreach ($attempt in 1..40) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw 'SHADOW_NOT_READY' }

    $openApi = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 5
    $paths = @($openApi.paths.PSObject.Properties.Name)
    $grantPath = '/api/v1/admin/desktop-workflow/devices/{agent_id}/enrollment-grants'
    $targetsPath = '/api/v1/admin/desktop-workflow/binding-targets'
    if ($grantPath -notin $paths -or $targetsPath -notin $paths) {
        throw 'ENROLLMENT_ROUTES_MISSING'
    }

    [pscustomobject]@{
        shadow_health = 'PASS'
        admin_grant_route = 'PASS'
        binding_targets_route = 'PASS'
    } | ConvertTo-Json -Compress
} finally {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener -and $process) {
        $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($listenerProcess -and [int]$listenerProcess.ParentProcessId -eq [int]$process.Id) {
            Stop-Process -Id ([int]$listener.OwningProcess) -Force -ErrorAction SilentlyContinue
        }
    }
    if ($process) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
}
