[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,
    [Parameter(Mandatory = $true)]
    [string]$BindingPath,
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentId,
    [Parameter(Mandatory = $true)]
    [string]$SourceCommit,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [switch]$SkipConfirmation
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$database = [System.IO.Path]::GetFullPath($DatabasePath)
$binding = [System.IO.Path]::GetFullPath($BindingPath)
$evidence = [System.IO.Path]::GetFullPath($EvidenceRoot)
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'ENGINE_PYTHON_MISSING' }
if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw 'ENGINE_DATABASE_MISSING' }
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

$timestamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$backup = Join-Path $evidence "channel-engine-before-$timestamp.sqlite3"
$clone = Join-Path $evidence "channel-engine-preflight-$timestamp.sqlite3"
$cloneBinding = Join-Path $evidence "channel-engine-preflight-$timestamp.binding.json"
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$databaseTool = Join-Path $repoRoot 'scripts\support\manage_channel_engine_database.py'

& $python $databaseTool backup --source $database --target $backup | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_DATABASE_BACKUP_FAILED' }
Copy-Item -LiteralPath $backup -Destination $clone -Force

& $python $databaseTool upgrade --database $clone | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_SCHEMA_PREFLIGHT_FAILED' }
& $python -m channel_engine.storage.runtime_database_identity bind-new `
    --database $clone --binding $cloneBinding --environment-id $EnvironmentId `
    --source-commit $SourceCommit | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_IDENTITY_PREFLIGHT_FAILED' }

$action = "upgrade and bind Channel Engine database $database"
if (-not $SkipConfirmation -and -not $PSCmdlet.ShouldProcess($database, $action)) {
    Write-Output '{"status":"CANCELLED_AFTER_PREFLIGHT"}'
    return
}

& $python $databaseTool upgrade --database $database | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_SCHEMA_UPGRADE_FAILED' }

$identityEvidence = (& $python $databaseTool identity-count --database $backup) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_IDENTITY_INSPECTION_FAILED' }
$bindingCommand = if ([int]$identityEvidence.identity_count -eq 1) { 'upgrade' } else { 'bind-new' }
& $python -m channel_engine.storage.runtime_database_identity $bindingCommand `
    --database $database --binding $binding --environment-id $EnvironmentId `
    --source-commit $SourceCommit | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_DATABASE_BINDING_FAILED' }
& $python -m channel_engine.storage.runtime_database_identity validate `
    --database $database --binding $binding --environment-id $EnvironmentId | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ENGINE_DATABASE_VALIDATION_FAILED' }

$result = [ordered]@{
    status = 'PASS'
    database = $database
    binding = $binding
    backup = $backup
    preflight_clone = $clone
    identity_mode = $bindingCommand
    whole_file_sha_usage = 'BACKUP_EVIDENCE_ONLY'
    backup_sha256 = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result | ConvertTo-Json -Depth 4
