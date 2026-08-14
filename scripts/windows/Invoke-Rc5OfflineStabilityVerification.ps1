[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AiCsRoot,
    [ValidateSet('Quick','Full')]
    [string]$Mode = 'Quick',
    [string]$EvidenceRoot = '.runtime\rc5-offline-stability\verification'
)

$ErrorActionPreference = 'Stop'
$engineRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$aiCs = [IO.Path]::GetFullPath($AiCsRoot)
$evidence = [IO.Path]::GetFullPath((Join-Path $engineRoot $EvidenceRoot))
if (-not (Test-Path -LiteralPath (Join-Path $aiCs 'backend') -PathType Container)) {
    throw 'AI_CS_ROOT_INVALID'
}
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

$results = [Collections.Generic.List[object]]::new()
function Invoke-Gate(
    [string]$Name,
    [string]$WorkingDirectory,
    [string]$Executable,
    [string[]]$Arguments
) {
    $started = [DateTimeOffset]::UtcNow
    $log = Join-Path $evidence ($Name + '.log')
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $Executable @Arguments 2>&1 | Tee-Object -FilePath $log
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $finished = [DateTimeOffset]::UtcNow
    $result = [ordered]@{
        name = $Name
        status = if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }
        exit_code = $exitCode
        duration_seconds = [Math]::Round(($finished - $started).TotalSeconds, 3)
        log = $log
    }
    $results.Add($result)
    if ($exitCode -ne 0) { throw "RC5 stability gate failed: $Name" }
}

$enginePython = Join-Path $engineRoot '.venv\Scripts\python.exe'
$backendPython = Join-Path $aiCs 'backend\.venv\Scripts\python.exe'
$platformPython = Join-Path $aiCs 'platform_backend\.venv\Scripts\python.exe'

if ($Mode -eq 'Full') {
    Invoke-Gate 'engine-full' $engineRoot $enginePython @('-m','pytest','-q')
    Invoke-Gate 'ai-cs-backend-full' (Join-Path $aiCs 'backend') $backendPython @('-m','pytest','-q')
    Invoke-Gate 'platform-full' (Join-Path $aiCs 'platform_backend') $platformPython @('-m','pytest','-q')
} else {
    Invoke-Gate 'engine-offline-critical' $engineRoot $enginePython @(
        '-m','pytest','-q',
        'tests\e2e\test_offline_complete_blackbox_v1.py',
        'tests\integration\test_runtime_database_identity_v1.py',
        'tests\unit\test_manage_channel_engine_database.py',
        'tests\unit\test_real_pdd_adapter_foundation_v1.py'
    )
    Invoke-Gate 'platform-governance' (Join-Path $aiCs 'platform_backend') $platformPython @(
        '-m','pytest','-q',
        'tests\test_runtime_database_identity.py',
        'tests\test_sqlite_backup_tool.py',
        'tests\test_production_hardening_migration.py',
        'tests\test_store_platform_binding_migration.py'
    )
}

Invoke-Gate 'contracts' $aiCs $backendPython @('-m','pytest','tests\contract','-q')
Invoke-Gate 'assistant-ui' (Join-Path $aiCs 'frontend') 'npm.cmd' @('test')
Invoke-Gate 'assistant-ui-typecheck' (Join-Path $aiCs 'frontend') 'npm.cmd' @('run','typecheck')
Invoke-Gate 'admin-ui' (Join-Path $aiCs 'admin_web') 'npm.cmd' @('test')
Invoke-Gate 'admin-ui-typecheck' (Join-Path $aiCs 'admin_web') 'npm.cmd' @('run','typecheck')
if ($Mode -eq 'Full') {
    Invoke-Gate 'assistant-ui-build' (Join-Path $aiCs 'frontend') 'npm.cmd' @('run','build')
    Invoke-Gate 'assistant-agent-ui-build' (Join-Path $aiCs 'frontend') 'npm.cmd' @('run','build:agent')
    Invoke-Gate 'admin-ui-build' (Join-Path $aiCs 'admin_web') 'npm.cmd' @('run','build')
}

$report = [ordered]@{
    schema = 'rc5-offline-stability-verification.v1'
    mode = $Mode.ToUpperInvariant()
    status = 'PASS'
    engine_commit = (& git -C $engineRoot rev-parse HEAD).Trim()
    ai_cs_commit = (& git -C $aiCs rev-parse HEAD).Trim()
    real_pdd_accessed = $false
    real_execution_attempts = 0
    real_sends = 0
    real_receipts = 0
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    results = $results
}
$reportPath = Join-Path $evidence 'verification-report.json'
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Output "status=PASS"
Write-Output "report=$reportPath"
