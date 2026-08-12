[CmdletBinding()]
param(
    [string]$PackageRoot = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent'),
    [string]$BaselinePackageRoot = (Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent'),
    [string]$Archive = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent-2.0.0rc5-windows-x64.zip'),
    [string]$ExpectedArchiveSha256 = '8d88d304ce8c25204c444a4c542f6e4784bb10fe05c4847e48bf3057c0fae5dc',
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '.runtime'))
$PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
$BaselinePackageRoot = [System.IO.Path]::GetFullPath($BaselinePackageRoot)
$Archive = [System.IO.Path]::GetFullPath($Archive)
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $prefix = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $candidate = [System.IO.Path]::GetFullPath($Child)
    if (-not $candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside isolated validation root: $candidate"
    }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Add-Check([System.Collections.Generic.List[object]]$Checks, [string]$Name, [bool]$Passed, [string]$Detail) {
    $Checks.Add([ordered]@{
        name = $Name
        status = $(if ($Passed) { 'PASS' } else { 'FAIL' })
        detail = $Detail
    })
    if (-not $Passed) { throw "Deployment check failed: $Name ($Detail)" }
}

Assert-ChildPath $allowedRoot $OutputRoot
foreach ($path in @($PackageRoot, $BaselinePackageRoot)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Package root is missing: $path" }
}
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) { throw 'RC5 archive is missing.' }
if (Test-Path -LiteralPath $OutputRoot) {
    Assert-ChildPath $allowedRoot $OutputRoot
    Remove-Item -LiteralPath $OutputRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$caseRoot = Join-Path $OutputRoot 'isolated-case'
$installRoot = Join-Path $caseRoot 'install'
$dataRoot = Join-Path $caseRoot 'data'
$startupRoot = Join-Path $caseRoot 'startup'
$invalidRoot = Join-Path $caseRoot 'invalid-package'
$checks = [System.Collections.Generic.List[object]]::new()
$result = [ordered]@{
    schema_version = 'rc5-windows-deployment.v1'
    started_at = [DateTimeOffset]::UtcNow.ToString('o')
    scope = 'ISOLATED_WORKSPACE_ONLY'
    current_installed_instance_mutations = 0
    package_root = $PackageRoot
    baseline_package_root = $BaselinePackageRoot
    checks = $checks
    status = 'STARTED'
}

try {
    $manifest = Get-Content -LiteralPath (Join-Path $PackageRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Add-Check $checks 'package_version_matrix' (
        $manifest.version -eq '2.0.0rc5' -and
        $manifest.agent_runtime_version -eq '2.0.0rc5' -and
        $manifest.channel_engine_compatibility -eq '0.2.0rc3' -and
        $manifest.agent_control_protocol -eq '2.1' -and
        $manifest.gateway_contract_sha256 -eq 'e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5'
    ) 'source/build/package compatibility fields are frozen'

    $invalidFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($file in @($manifest.files)) {
        $candidate = Join-Path $PackageRoot ([string]$file.path).Replace('/', '\')
        if (
            -not (Test-Path -LiteralPath $candidate -PathType Leaf) -or
            (Get-Sha256 $candidate) -ne [string]$file.sha256
        ) { $invalidFiles.Add([string]$file.path) }
    }
    Add-Check $checks 'release_manifest_file_integrity' ($invalidFiles.Count -eq 0) "validated $(@($manifest.files).Count) files"
    $archiveSha = Get-Sha256 $Archive
    Add-Check $checks 'archive_sha256' ($archiveSha -eq $ExpectedArchiveSha256.ToLowerInvariant()) $archiveSha

    $baselineInstaller = Join-Path $BaselinePackageRoot 'install\Install-AI-CS-Channel-Agent.ps1'
    & $baselineInstaller `
        -PackageRoot $BaselinePackageRoot `
        -InstallRoot $installRoot `
        -DataRoot $dataRoot `
        -StartupDirectory $startupRoot `
        -EnableAutoStart `
        -Force | Out-Null
    Add-Check $checks 'fresh_install' (Test-Path -LiteralPath (Join-Path $installRoot 'ChannelAgent.exe') -PathType Leaf) 'baseline package installed into isolated root'
    Add-Check $checks 'temporary_autostart' (Test-Path -LiteralPath (Join-Path $startupRoot 'AI-CS-Channel-Agent.cmd') -PathType Leaf) 'autostart created only in isolated startup directory'

    New-Item -ItemType Directory -Path (Join-Path $dataRoot 'config') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $dataRoot 'runtime\pdd-login') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $dataRoot 'browser\profiles\rc5-test\edge\Default\Sessions') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $BaselinePackageRoot 'config\agent.offline-replay.example.json') -Destination (Join-Path $dataRoot 'config\agent.json') -Force
    [ordered]@{
        agent_id = 'agent-rc5-isolated-test'
        device_id = 'device-rc5-isolated-test'
        identity_status = 'ACTIVE'
        binding_revision = 7
        authorized_store_ids = @('store-rc5-isolated-test')
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'runtime\agent-binding.json') -Encoding UTF8
    [ordered]@{ device_id = 'device-rc5-isolated-test'; schema_version = '1.0' } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'runtime\bootstrap-device.json') -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $dataRoot 'runtime\pdd-login\session.sentinel') -Value 'synthetic-session-sentinel' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $dataRoot 'browser\profiles\rc5-test\edge\Default\Sessions\profile.sentinel') -Value 'synthetic-profile-sentinel' -Encoding UTF8
    $protected = @(
        'config\agent.json',
        'runtime\agent-binding.json',
        'runtime\bootstrap-device.json',
        'runtime\pdd-login\session.sentinel',
        'browser\profiles\rc5-test\edge\Default\Sessions\profile.sentinel'
    )
    $beforeHashes = [ordered]@{}
    foreach ($relative in $protected) { $beforeHashes[$relative] = Get-Sha256 (Join-Path $dataRoot $relative) }

    $finalInstaller = Join-Path $PackageRoot 'install\Install-AI-CS-Channel-Agent.ps1'
    & $finalInstaller `
        -PackageRoot $PackageRoot `
        -InstallRoot $installRoot `
        -DataRoot $dataRoot `
        -StartupDirectory $startupRoot `
        -EnableAutoStart `
        -Force | Out-Null
    $afterHashes = [ordered]@{}
    foreach ($relative in $protected) { $afterHashes[$relative] = Get-Sha256 (Join-Path $dataRoot $relative) }
    Add-Check $checks 'upgrade_preserves_identity_binding_profile_session' ((ConvertTo-Json $beforeHashes -Compress) -eq (ConvertTo-Json $afterHashes -Compress)) 'all five protected isolated files retained exact SHA256'

    $runtimeVersion = (& (Join-Path $installRoot 'runtime\python\python.exe') (Join-Path $installRoot 'app\channel-agent.pyz') version).Trim()
    Add-Check $checks 'installed_runtime_version' ($runtimeVersion -eq '2.0.0rc5') $runtimeVersion
    $installedManifest = Get-Content -LiteralPath (Join-Path $installRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Add-Check $checks 'installed_manifest_version' ($installedManifest.agent_runtime_version -eq $runtimeVersion) "manifest=$($installedManifest.agent_runtime_version), runtime=$runtimeVersion"

    New-Item -ItemType Directory -Path $invalidRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'release-manifest.json') -Destination $invalidRoot
    $beforeRejectedUpgrade = Get-Sha256 (Join-Path $installRoot 'app\channel-agent.pyz')
    $rejected = $false
    try {
        & $finalInstaller -PackageRoot $invalidRoot -InstallRoot $installRoot -DataRoot $dataRoot -Force | Out-Null
    }
    catch { $rejected = $true }
    $afterRejectedUpgrade = Get-Sha256 (Join-Path $installRoot 'app\channel-agent.pyz')
    Add-Check $checks 'invalid_upgrade_fails_before_mutation' ($rejected -and $beforeRejectedUpgrade -eq $afterRejectedUpgrade) 'missing required package files rejected; installed runtime unchanged'

    $uninstaller = Join-Path $installRoot 'install\Uninstall-AI-CS-Channel-Agent.ps1'
    & $uninstaller -InstallRoot $installRoot -DataRoot $dataRoot -StartupDirectory $startupRoot | Out-Null
    Add-Check $checks 'uninstall_preserves_data' (-not (Test-Path -LiteralPath $installRoot) -and (Test-Path -LiteralPath $dataRoot -PathType Container)) 'install removed and data retained'
    Add-Check $checks 'uninstall_disables_autostart' (-not (Test-Path -LiteralPath (Join-Path $startupRoot 'AI-CS-Channel-Agent.cmd'))) 'isolated autostart removed'

    & $finalInstaller -PackageRoot $PackageRoot -InstallRoot $installRoot -DataRoot $dataRoot -Force | Out-Null
    $reinstallHashes = [ordered]@{}
    foreach ($relative in $protected) { $reinstallHashes[$relative] = Get-Sha256 (Join-Path $dataRoot $relative) }
    Add-Check $checks 'reinstall_preserves_data' ((ConvertTo-Json $beforeHashes -Compress) -eq (ConvertTo-Json $reinstallHashes -Compress)) 'reinstall retained identity, binding, Profile and session sentinels'

    $uninstaller = Join-Path $installRoot 'install\Uninstall-AI-CS-Channel-Agent.ps1'
    & $uninstaller -InstallRoot $installRoot -DataRoot $dataRoot -StartupDirectory $startupRoot -RemoveData | Out-Null
    Add-Check $checks 'explicit_remove_data' (-not (Test-Path -LiteralPath $installRoot) -and -not (Test-Path -LiteralPath $dataRoot)) 'generated test install and data removed explicitly'
    $result.status = 'PASS'
    $result.archive_sha256 = $archiveSha
    $result.package_executable_sha256 = Get-Sha256 (Join-Path $PackageRoot 'ChannelAgent.exe')
    $result.package_runtime_sha256 = Get-Sha256 (Join-Path $PackageRoot 'app\channel-agent.pyz')
}
catch {
    $result.status = 'FAIL'
    $result.error = $_.Exception.Message
    throw
}
finally {
    $result.completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    $report = Join-Path $OutputRoot 'windows-deployment-report.json'
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $report -Encoding UTF8
    Write-Output "status=$($result.status)"
    Write-Output "report=$report"
}
