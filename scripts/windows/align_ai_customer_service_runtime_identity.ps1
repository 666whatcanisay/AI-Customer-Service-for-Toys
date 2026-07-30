[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PreviousGitSha,
    [string]$ConfigPath,
    [ValidateSet('Local', 'Lan')]
    [string]$NetworkProfile = 'Lan'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

function Test-AlignmentHttpOk([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
        return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 400
    } catch {
        return $false
    }
}

$baseConfig = Get-LocalConfig $ConfigPath
if ((Get-ConfiguredRuntimeMode $baseConfig) -ne 'standard') {
    throw '正式身份对齐只接受 RuntimeMode=standard。'
}
if ($NetworkProfile -eq 'Lan') {
    $config = Resolve-LanRuntimeConfig $baseConfig
} else {
    $config = $baseConfig
}
$repositoryRoot = [IO.Path]::GetFullPath([string]$config.RepositoryRoot)
$currentIdentity = Get-RepositoryRuntimeIdentity $repositoryRoot
if (-not $currentIdentity.Available -or $currentIdentity.SourceState -ne 'CLEAN') {
    throw "当前仓库必须可解析且为 CLEAN：$($currentIdentity.Reason)"
}
$PreviousGitSha = $PreviousGitSha.Trim().ToLowerInvariant()
if ($PreviousGitSha -notmatch '^[0-9a-f]{40}$') { throw 'PreviousGitSha 必须是完整40位Git SHA。' }
& git -C $repositoryRoot cat-file -e "$PreviousGitSha^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PreviousGitSha 不可解析：$PreviousGitSha" }
& git -C $repositoryRoot merge-base --is-ancestor $PreviousGitSha $currentIdentity.GitSha
if ($LASTEXITCODE -ne 0) { throw 'PreviousGitSha 不是当前HEAD祖先，拒绝重新证明。' }

$changedPaths = @(& git -C $repositoryRoot diff --name-only $PreviousGitSha $currentIdentity.GitSha --)
if ($LASTEXITCODE -ne 0) { throw '无法读取身份对齐版本差异。' }
$unexpectedPaths = @($changedPaths | Where-Object {
    $_ -notlike 'scripts/windows/*' -and $_ -notlike 'docs/rag/*' -and $_ -notlike 'docs/control/*'
})
if ($unexpectedPaths.Count -gt 0) {
    throw "身份对齐版本包含业务或非OPS变更：$($unexpectedPaths -join '，')"
}

$services = @(
    @{ Name='platform'; Port=[int]$config.PlatformPort; HealthUrl=(Get-ServiceUrl $config $config.PlatformPort $config.PlatformHealthPath) },
    @{ Name='rag'; Port=[int]$config.RagPort; HealthUrl=(Get-ServiceUrl $config $config.RagPort $config.RagHealthPath) },
    @{ Name='customer-web'; Port=[int]$config.CustomerWebPort; HealthUrl=[string]$config.CustomerWebUrl },
    @{ Name='admin-web'; Port=[int]$config.AdminWebPort; HealthUrl=(Get-ManagedServiceHealthUrl $config 'admin-web') }
)
$originalRecords = @{}
$recordObjects = @{}
foreach ($service in $services) {
    $name = [string]$service.Name
    $recordPath = Get-ServiceRecordPath $config $name
    if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) { throw "$name 缺少运行记录：$recordPath" }
    $originalJson = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8
    $record = $originalJson | ConvertFrom-Json
    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$record.repository_root), $repositoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$name 的repository root不匹配。"
    }
    if (-not [string]::Equals([string]$record.repository_git_sha, $PreviousGitSha, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$name 的记录SHA不是指定前序版本。"
    }
    $processCheck = Test-RecordedProcess $config $name -Detailed
    if (-not $processCheck.Valid) { throw "$name PID身份无法验证：$($processCheck.Reason)" }
    $owners = @(Get-PortOwner ([int]$service.Port))
    if ($owners.Count -ne 1 -or [int]$owners[0] -ne [int]$record.listener_pid) {
        throw "$name 监听PID与端口所有者不一致。"
    }
    if (-not (Test-AlignmentHttpOk ([string]$service.HealthUrl))) { throw "$name 健康检查失败：$($service.HealthUrl)" }
    $originalRecords[$name] = $originalJson
    $recordObjects[$name] = $record
}

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$backupDirectory = Join-Path $config.RuntimeDirectory "identity-alignment-backups\$timestamp"
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
foreach ($service in $services) {
    $name = [string]$service.Name
    $originalRecords[$name] | Set-Content -LiteralPath (Join-Path $backupDirectory "$name.json") -Encoding UTF8
}

try {
    foreach ($service in $services) {
        $name = [string]$service.Name
        $record = $recordObjects[$name]
        $record | Add-Member -NotePropertyName repository_git_sha -NotePropertyValue $currentIdentity.GitSha -Force
        $record | Add-Member -NotePropertyName repository_source_state -NotePropertyValue $currentIdentity.SourceState -Force
        $record | Add-Member -NotePropertyName repository_source_fingerprint -NotePropertyValue $currentIdentity.SourceFingerprint -Force
        $record | Add-Member -NotePropertyName runtime_mode -NotePropertyValue (Get-ConfiguredRuntimeMode $config) -Force
        $record | Add-Member -NotePropertyName network_mode -NotePropertyValue (Get-ConfiguredNetworkMode $config) -Force
        $record | Add-Member -NotePropertyName identity_aligned_from_git_sha -NotePropertyValue $PreviousGitSha -Force
        $record | Add-Member -NotePropertyName identity_aligned_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
        $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Get-ServiceRecordPath $config $name) -Encoding UTF8
    }

    foreach ($service in $services) {
        $name = [string]$service.Name
        $processCheck = Test-RecordedProcess $config $name -Detailed
        $record = $processCheck.Record
        $identityCheck = Test-ManagedServiceRuntimeIdentity $config $record
        if (-not $processCheck.Valid -or -not $identityCheck.Valid -or -not (Test-AlignmentHttpOk ([string]$service.HealthUrl))) {
            throw "$name 对齐后验证失败：process=$($processCheck.Valid)；identity=$($identityCheck.Valid)"
        }
    }
} catch {
    foreach ($service in $services) {
        $name = [string]$service.Name
        $originalRecords[$name] | Set-Content -LiteralPath (Get-ServiceRecordPath $config $name) -Encoding UTF8
    }
    throw
}

[ordered]@{
    aligned_at_utc = [DateTime]::UtcNow.ToString('o')
    repository_root = $repositoryRoot
    previous_git_sha = $PreviousGitSha
    current_git_sha = $currentIdentity.GitSha
    runtime_mode = Get-ConfiguredRuntimeMode $config
    network_mode = Get-ConfiguredNetworkMode $config
    config_path = [IO.Path]::GetFullPath($ConfigPath)
    config_sha256 = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash.ToLowerInvariant()
    backup_directory = $backupDirectory
    services = @($services | ForEach-Object { [ordered]@{ name=$_.Name; port=$_.Port; health_url=$_.HealthUrl } })
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $backupDirectory 'alignment-manifest.json') -Encoding UTF8

Write-Host "Runtime身份已无停机对齐：runtimeMode=$(Get-ConfiguredRuntimeMode $config)；networkMode=$(Get-ConfiguredNetworkMode $config)；SHA=$($currentIdentity.GitSha)" -ForegroundColor Green
Write-Host "运行记录备份：$backupDirectory"
