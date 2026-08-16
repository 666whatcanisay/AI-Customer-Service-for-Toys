[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AiCsRoot,
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot
)

$ErrorActionPreference = 'Stop'
$aiCsRoot = [System.IO.Path]::GetFullPath($AiCsRoot)
$configPath = [System.IO.Path]::GetFullPath($ConfigPath)
$evidenceRoot = [System.IO.Path]::GetFullPath($EvidenceRoot)
$common = Join-Path $aiCsRoot 'scripts\windows\common_ai_customer_service.ps1'
if (-not (Test-Path -LiteralPath $common -PathType Leaf)) {
    throw "RC5_AI_CS_COMMON_MISSING:$common"
}
if (Get-NetTCPConnection -State Listen -LocalPort 8420 -ErrorAction SilentlyContinue) {
    throw 'RC5_AI_CS_PORT_8420_ALREADY_IN_USE'
}

. $common
$config = Get-LocalConfig $configPath
$environment = Get-LocalRagEnvironment $config
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
$process = Invoke-WithProcessEnvironment $environment {
    Start-Process -FilePath $config.RagPythonPath -ArgumentList @(
        '-m', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1', '--port', '8420', '--no-access-log'
    ) -WorkingDirectory (Join-Path $aiCsRoot 'backend') -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $evidenceRoot 'ai-cs.stdout.log') `
        -RedirectStandardError (Join-Path $evidenceRoot 'ai-cs.stderr.log') `
        -PassThru
}

$ready = $false
foreach ($attempt in 1..120) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8420/api/health' -TimeoutSec 2
        if ($health.success -and $health.data.ready) {
            $ready = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    throw "RC5_AI_CS_NOT_READY:$($process.Id)"
}

$listener = Get-NetTCPConnection -State Listen -LocalPort 8420 |
    Select-Object -First 1
[pscustomobject]@{
    pid = $listener.OwningProcess
    launcher_pid = $process.Id
    source_root = $aiCsRoot
    health = 'ok'
    real_pdd = $false
    real_send = $false
} | ConvertTo-Json -Compress
