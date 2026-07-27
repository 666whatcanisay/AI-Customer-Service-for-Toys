[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$ConfirmBackup
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

if (-not $ConfirmBackup) {
    Write-Error 'Pilot data backup requires -ConfirmBackup. No database was read or copied.'
    exit 2
}

function Get-TargetPilotSqlitePath($Config) {
    $databaseUrl = [string]$Config.PlatformDatabaseUrl
    $prefix = 'sqlite:///'
    if (-not $databaseUrl.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only a repository-local SQLite database is supported by this pilot backup tool.'
    }
    $relativePath = $databaseUrl.Substring($prefix.Length)
    if ([string]::IsNullOrWhiteSpace($relativePath) -or $relativePath -match '[?#]') {
        throw 'The platform SQLite database path is invalid for the pilot backup tool.'
    }
    $platformDirectory = [IO.Path]::GetFullPath((Join-Path $Config.RepositoryRoot 'platform_backend'))
    $databasePath = if ($relativePath -match '^[A-Za-z]:[\\/]') {
        [IO.Path]::GetFullPath($relativePath)
    } else {
        [IO.Path]::GetFullPath((Join-Path $platformDirectory $relativePath))
    }
    $repositoryDirectory = [IO.Path]::GetFullPath($Config.RepositoryRoot)
    $repositoryPrefix = $repositoryDirectory.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $databasePath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The platform SQLite database must remain inside the repository.'
    }
    if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw 'The configured platform SQLite database does not exist.'
    }
    return $databasePath
}

try {
    $config = Get-LocalConfig $ConfigPath
    $sourceDatabase = Get-TargetPilotSqlitePath $config
    $backupDirectory = Join-Path $config.RuntimeDirectory 'pilot-backups'
    New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupFileName = "platform-$timestamp.sqlite3"
    $backupPath = Join-Path $backupDirectory $backupFileName
    $pythonProgram = 'import sqlite3, sys; source, target = sys.argv[1:3]; source_db = sqlite3.connect(source); target_db = sqlite3.connect(target); source_db.backup(target_db); target_db.close(); source_db.close()'
    & $config.PlatformPythonPath -c $pythonProgram $sourceDatabase $backupPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
        throw 'The SQLite online backup command did not produce a backup file.'
    }
    $metadata = [ordered]@{
        schemaVersion = 'target-pilot-backup.v1'
        createdUtc = [DateTime]::UtcNow.ToString('o')
        databaseKind = 'sqlite'
        backupFile = $backupFileName
        byteLength = [int64](Get-Item -LiteralPath $backupPath).Length
        contentsLogged = $false
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupDirectory "platform-$timestamp.json") -Encoding UTF8
    Write-Host "Pilot SQLite backup completed: $backupFileName (metadata only; no database content was printed)." -ForegroundColor Green
} catch {
    Write-Error 'Pilot data backup did not complete. No database content was printed or committed.'
    exit 1
}
