[CmdletBinding()]
param(
    [string]$AiCsRoot,
    [string]$EngineDatabasePath,
    [string]$PlatformDatabasePath,
    [string]$PlatformBindingPath,
    [string]$PlatformActivationPath,
    [string]$RagActivationPath,
    [string]$HostActivationPath,
    [string]$AiCsConfigPath,
    [string]$AgentConfigPath,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $PSScriptRoot 'Resolve-AiCsRepositoryRoot.ps1')
$aiCsRoot = Resolve-AiCsRepositoryRoot $repoRoot $AiCsRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$governanceScript = Join-Path $repoRoot 'scripts\rc5_pilot_governance.py'
$governanceRoot = Join-Path $repoRoot '.runtime\rc5-pilot-governance'
$catalogPath = Join-Path $governanceRoot 'runtime-catalog.json'
$factsPath = Join-Path $repoRoot 'docs\production\rc5-final\RC5-Offline-Stability-Version-Matrix.json'
$aiCsCommonScript = Join-Path $aiCsRoot 'scripts\windows\common_ai_customer_service.ps1'

if (-not $EngineDatabasePath) { $EngineDatabasePath = Join-Path $repoRoot '.runtime\channel-engine.sqlite3' }
if (-not $PlatformDatabasePath) { $PlatformDatabasePath = Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\runtime\platform.sqlite3' }
if (-not $PlatformBindingPath) { $PlatformBindingPath = "$PlatformDatabasePath.binding.json" }
if (-not $HostActivationPath) { $HostActivationPath = Join-Path $repoRoot '.runtime\rc5-manual-start\rc5-pilot-governance\activations\channel-engine-host.json' }
if (-not $PlatformActivationPath) { $PlatformActivationPath = Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\runtime\managed\rc5-pilot-governance\activations\ai-cs-platform.json' }
if (-not $RagActivationPath) { $RagActivationPath = Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\runtime\managed\rc5-pilot-governance\activations\ai-cs-rag.json' }
if (-not $AiCsConfigPath) { $AiCsConfigPath = Join-Path $aiCsRoot '.runtime\r027-ux-acceptance-data-v1\ux-acceptance.local.ps1' }
if (-not $AgentConfigPath) { $AgentConfigPath = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent\config\agent.json' }
if (-not $OutputPath) { $OutputPath = Join-Path $governanceRoot 'latest-status.json' }

foreach ($required in @($python,$governanceScript,$factsPath,$EngineDatabasePath,"$EngineDatabasePath.binding.json",$PlatformDatabasePath,$PlatformBindingPath,$HostActivationPath,$PlatformActivationPath,$RagActivationPath,$AiCsConfigPath,$aiCsCommonScript,$AgentConfigPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "RC5_PILOT_STATUS_DEPENDENCY_MISSING:$required"
    }
}
New-Item -ItemType Directory -Path $governanceRoot -Force | Out-Null

$specs = @(
    [ordered]@{
        name = 'channel-engine-host'
        component = 'CHANNEL_ENGINE_HOST'
        database_path = [IO.Path]::GetFullPath($EngineDatabasePath)
        binding_path = [IO.Path]::GetFullPath("$EngineDatabasePath.binding.json")
    },
    [ordered]@{
        name = 'ai-cs-platform'
        component = 'AI_CS_PLATFORM'
        database_path = [IO.Path]::GetFullPath($PlatformDatabasePath)
        binding_path = [IO.Path]::GetFullPath($PlatformBindingPath)
    }
)
$specPaths = @()
foreach ($spec in $specs) {
    $path = Join-Path $governanceRoot "$($spec.name).active.json"
    $temporary = "$path.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $spec | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $path -Force
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
    $specPaths += $path
}

$previousPythonPath = $env:PYTHONPATH
$previousInternalServiceToken = $env:AI_CS_PILOT_INTERNAL_SERVICE_TOKEN
try {
    . $aiCsCommonScript
    $aiCsConfig = Get-LocalConfig $AiCsConfigPath
    $env:AI_CS_PILOT_INTERNAL_SERVICE_TOKEN = Get-AiCsInternalServiceToken $aiCsConfig
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $catalogArgs = @(
        $governanceScript,'catalog',
        '--scan-root',(Join-Path $repoRoot '.runtime'),
        '--scan-root',(Join-Path $aiCsRoot '.runtime'),
        '--active-spec',$specPaths[0],
        '--active-spec',$specPaths[1],
        '--expected-active-role','RC5_CHANNEL_ENGINE_LOCAL|HOST_CONTROL',
        '--expected-active-role','RC5_R027_UX_ACCEPTANCE|PLATFORM',
        '--output',$catalogPath
    )
    & $python @catalogArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "RC5_RUNTIME_CATALOG_BLOCKED:$LASTEXITCODE" }

    & $python $governanceScript status `
        --facts $factsPath `
        --catalog $catalogPath `
        --activation $HostActivationPath `
        --activation $PlatformActivationPath `
        --activation $RagActivationPath `
        --agent-config $AgentConfigPath `
        --output $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "RC5_PILOT_STATUS_BLOCKED:${LASTEXITCODE}。请查看 $OutputPath" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    if ($null -eq $previousInternalServiceToken) {
        Remove-Item Env:AI_CS_PILOT_INTERNAL_SERVICE_TOKEN -ErrorAction SilentlyContinue
    } else {
        $env:AI_CS_PILOT_INTERNAL_SERVICE_TOKEN = $previousInternalServiceToken
    }
}

Write-Host "RC5 Pilot 状态：PASS" -ForegroundColor Green
Write-Host "当前状态文件：$([IO.Path]::GetFullPath($OutputPath))"
Write-Host "Runtime Catalog：$([IO.Path]::GetFullPath($catalogPath))"
