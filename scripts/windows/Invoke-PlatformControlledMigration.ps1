[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [string]$ConfigPath,
    [Parameter(Mandatory)] [ValidateSet('NEW_INSTANCE','UPGRADE','RESTORE')] [string]$IdentityMode,
    [string]$BackupEpoch = '',
    [switch]$SkipConfirmation
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

$config = Get-LocalConfig $ConfigPath
$databasePath = [IO.Path]::GetFullPath([string]$config.PlatformDatabasePath)
$bindingPath = [IO.Path]::GetFullPath([string]$config.PlatformDatabaseBindingPath)
$platformRoot = Join-Path $config.RepositoryRoot 'platform_backend'
if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) { throw "Database does not exist: $databasePath" }
if ((Get-Item -LiteralPath $databasePath).Length -le 16) { throw "Database is empty or truncated: $databasePath" }
if ($IdentityMode -eq 'RESTORE' -and [string]::IsNullOrWhiteSpace($BackupEpoch)) { throw 'RESTORE requires -BackupEpoch.' }

$backupDirectory = Join-Path $config.RuntimeDirectory ('database-migrations\' + [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
$backupPath = Join-Path $backupDirectory 'platform.pre-migration.sqlite3'
$clonePath = Join-Path $backupDirectory 'platform.migration-preflight.sqlite3'
$evidencePath = Join-Path $backupDirectory 'migration-evidence.json'
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null

$sourceCommit = (& git -C $config.RepositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sourceCommit)) { throw 'Cannot resolve source commit.' }

function Invoke-SqliteBackup([string]$Source, [string]$Target) {
    $tool = Join-Path $config.RepositoryRoot 'scripts\support\backup_sqlite_database.py'
    & $config.PlatformPythonPath $tool --source $Source --target $Target | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "SQLite online backup failed: $Target" }
}

Invoke-SqliteBackup $databasePath $backupPath
Copy-Item -LiteralPath $backupPath -Destination $clonePath
$cloneUrl = 'sqlite:///' + ($clonePath.Replace('\','/'))
Push-Location -LiteralPath $platformRoot
try {
    $headOutput = @(& $config.PlatformPythonPath -m alembic heads)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the Platform Alembic head.' }
    $headRevisions = @(
        $headOutput | ForEach-Object {
            if ([string]$_ -match '^([^\s]+)\s+\(head\)$') { $Matches[1] }
        }
    )
    if ($headRevisions.Count -ne 1) {
        throw "Platform migrations must have exactly one head; found $($headRevisions.Count)."
    }
    $targetRevision = [string]$headRevisions[0]

    $envBefore = [Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('DATABASE_URL', $cloneUrl, 'Process')
        & $config.PlatformPythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Migration preflight failed.' }
        & $config.PlatformPythonPath -m app.runtime_database_identity bind-new `
            --database $clonePath `
            --binding ($clonePath + '.binding.json') `
            --environment-id ($config.PlatformDatabaseEnvironmentId + ':MIGRATION_PREFLIGHT') `
            --source-commit $sourceCommit | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Migration preflight identity binding failed.' }
    } finally {
        [Environment]::SetEnvironmentVariable('DATABASE_URL', $envBefore, 'Process')
    }

    if (-not $SkipConfirmation -and -not $PSCmdlet.ShouldProcess($databasePath, "backup, migrate to $targetRevision and bind runtime identity")) {
        Write-Host "Migration cancelled. Backup and preflight remain at: $backupDirectory"
        return
    }

    $platformEnvironment = Get-LocalPlatformEnvironment $config
    Invoke-WithProcessEnvironment $platformEnvironment {
        & $config.PlatformPythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Runtime database migration failed.' }
    }
    $identityCommand = if ($IdentityMode -eq 'RESTORE') {
        'mark-restored'
    } elseif ($IdentityMode -eq 'UPGRADE') {
        'mark-upgraded'
    } else {
        'bind-new'
    }
    $arguments = @(
        '-m','app.runtime_database_identity',$identityCommand,
        '--database',$databasePath,
        '--binding',$bindingPath,
        '--environment-id',$config.PlatformDatabaseEnvironmentId,
        '--source-commit',$sourceCommit
    )
    if ($IdentityMode -eq 'RESTORE') { $arguments += @('--backup-epoch',$BackupEpoch) }
    & $config.PlatformPythonPath @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Runtime database identity binding failed.' }
    Assert-PlatformDatabaseReady $config
} finally {
    Pop-Location
}

$databaseHash = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
$backupHash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{
    schema = 'ai-cs.platform-controlled-migration-evidence.v1'
    status = 'PASS'
    database_path = $databasePath
    binding_path = $bindingPath
    source_commit = $sourceCommit
    target_revision = $targetRevision
    identity_mode = $IdentityMode
    backup_epoch = if ($IdentityMode -eq 'RESTORE') { $BackupEpoch } else { $null }
    backup_path = $backupPath
    backup_sha256 = $backupHash
    post_migration_sha256 = $databaseHash
    verified_at = [datetime]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
Write-Host "Platform controlled migration PASS: $evidencePath" -ForegroundColor Green
