[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$PackageArchive,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent'),
    [string]$ExpectedArchiveSha256,
    [string]$ReportPath,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$PackageArchive = [System.IO.Path]::GetFullPath($PackageArchive)
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$shortcutHelperCandidates = @(
    (Join-Path $PSScriptRoot 'ChannelAgentShortcutName.ps1'),
    (Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentShortcutName.ps1')
)
$shortcutHelper = $shortcutHelperCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $shortcutHelper) { throw 'ChannelAgent shortcut naming helper is missing.' }
. $shortcutHelper

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ProcessByExactPath {
    param([Parameter(Mandatory = $true)][string]$ExecutablePath)
    $expected = [System.IO.Path]::GetFullPath($ExecutablePath)
    return @(Get-CimInstance Win32_Process -Filter "Name='ChannelAgent.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                $expected,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        })
}

function Test-ProcessId {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Read-AgentState {
    $path = Join-Path $DataRoot 'runtime\channel-agent-state.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'ChannelAgent runtime state is missing.'
    }
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-SafeStateView {
    param([Parameter(Mandatory = $true)]$State)
    return [ordered]@{
        client_version = $State.client_version
        agent_version = $State.agent_version
        runtime_pid = $State.pid
        process_status = $State.process_status
        runtime_status = $State.runtime_status
        identity_status = $State.identity_status
        agent_id = $State.agent_id
        device_id = $State.device_id
        user_id = $State.user_id
        authorized_store_ids = @($State.authorized_store_ids)
        active_store_id = $State.active_store_id
        binding_revision = $State.binding_revision
        browser_pid = $State.browser_pid
        browser_status = $State.browser_status
        browser_profile_reference = $State.browser_profile_reference
        pdd_login_state = $State.pdd_login_state
        pdd_store_reference = $State.pdd_store_reference
        desktop_ui_status = $State.desktop_ui_status
    }
}

function Assert-StateIdentityUnchanged {
    param(
        [Parameter(Mandatory = $true)]$Before,
        [Parameter(Mandatory = $true)]$After
    )
    foreach ($field in @(
        'agent_id',
        'device_id',
        'user_id',
        'identity_status',
        'active_store_id',
        'binding_revision',
        'browser_profile_reference'
    )) {
        if ([string]$Before.$field -ne [string]$After.$field) {
            throw "Protected runtime field changed during brand upgrade: $field"
        }
    }
    $beforeStores = @($Before.authorized_store_ids | Sort-Object)
    $afterStores = @($After.authorized_store_ids | Sort-Object)
    if (($beforeStores -join "`n") -ne ($afterStores -join "`n")) {
        throw 'Authorized stores changed during brand upgrade.'
    }
}

function Copy-BackupFile {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$BackupRoot
    )
    $source = Join-Path $InstallRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { return }
    $destination = Join-Path $BackupRoot $RelativePath
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Restore-BackupFile {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$BackupRoot
    )
    $backup = Join-Path $BackupRoot $RelativePath
    $target = Join-Path $InstallRoot $RelativePath
    if (Test-Path -LiteralPath $backup -PathType Leaf) {
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $backup -Destination $target -Force
    } elseif (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
    }
}

if (-not (Test-Path -LiteralPath $PackageArchive -PathType Leaf)) {
    throw "Brand package was not found: $PackageArchive"
}
if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
    throw "ChannelAgent install root was not found: $InstallRoot"
}

$archiveSha = Get-Sha256 $PackageArchive
if ($ExpectedArchiveSha256 -and $archiveSha -ne $ExpectedArchiveSha256.ToLowerInvariant()) {
    throw 'Official package SHA256 does not match the approved value.'
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("channel-agent-brand-upgrade-" + [guid]::NewGuid().ToString('N'))
$backupRoot = Join-Path $InstallRoot ('.brand-upgrade-backups\' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
$allowedAssets = @(
    'assets\branding\brand-build-manifest.json',
    'assets\branding\channel-agent.ico',
    'assets\branding\channel-agent-avatar.png',
    'assets\branding\channel-agent-tray-normal.ico',
    'assets\branding\channel-agent-tray-warning.ico',
    'assets\branding\channel-agent-tray-error.ico',
    'assets\branding\channel-agent-tray-offline.ico'
)
$protectedFiles = @(
    'app\channel-agent.pyz',
    'config\agent.example.json'
)
$backupFiles = @(
    'ChannelAgent.exe',
    'ui\index.html',
    'ui\channel-agent-avatar.png',
    'brand-upgrade-manifest.json'
) + $allowedAssets
$createdPaths = New-Object System.Collections.Generic.List[string]
$upgradeApplied = $false
$rollbackPerformed = $false
$shortcutCreated = $false
$report = $null

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    Expand-Archive -LiteralPath $PackageArchive -DestinationPath $tempRoot -Force
    $packageRoot = Join-Path $tempRoot 'AI-CS-Channel-Agent'
    if (-not (Test-Path -LiteralPath $packageRoot -PathType Container)) {
        $directories = @(Get-ChildItem -LiteralPath $tempRoot -Directory)
        if ($directories.Count -ne 1) { throw 'Official package has an unexpected root layout.' }
        $packageRoot = $directories[0].FullName
    }

    & (Join-Path $repoRoot 'scripts\validate_channel_agent_brand_package.ps1') -PackageRoot $packageRoot

    $packageManifest = Get-Content -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$packageManifest.version -ne '2.0.0rc2' -or [string]$packageManifest.branding_status -ne 'official') {
        throw 'The package is not the approved official ChannelAgent 2.0.0rc2 brand build.'
    }
    foreach ($relative in @('ChannelAgent.exe', 'ui\channel-agent-avatar.png') + $allowedAssets) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relative) -PathType Leaf)) {
            throw "Brand upgrade source is missing: $relative"
        }
    }

    $newExe = Get-Item -LiteralPath (Join-Path $packageRoot 'ChannelAgent.exe')
    if ($newExe.VersionInfo.FileVersion -ne '2.0.0.2' -or $newExe.VersionInfo.ProductVersion -ne '2.0.0rc2') {
        throw 'ChannelAgent.exe does not contain the required Windows 2.0.0rc2 version resources.'
    }

    $currentManifestPath = Join-Path $InstallRoot 'release-manifest.json'
    $currentManifest = Get-Content -LiteralPath $currentManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$currentManifest.agent_control_protocol -ne [string]$packageManifest.agent_control_protocol) {
        throw 'Agent Control protocol differs; brand-only upgrade is not allowed.'
    }

    $stateBeforeRaw = Read-AgentState
    $stateBefore = Get-SafeStateView $stateBeforeRaw
    if (-not (Test-ProcessId ([int]$stateBeforeRaw.pid))) {
        throw 'Agent Runtime is not running; refusing to disguise a runtime repair as a brand upgrade.'
    }
    $configPath = Join-Path $DataRoot 'config\agent.json'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Agent configuration is missing.' }
    $pyzPath = Join-Path $InstallRoot 'app\channel-agent.pyz'
    $configShaBefore = Get-Sha256 $configPath
    $pyzShaBefore = Get-Sha256 $pyzPath
    $trayBefore = @(Get-ProcessByExactPath (Join-Path $InstallRoot 'ChannelAgent.exe'))
    $edgeBefore = @(Get-Process -Name 'msedge' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $profileRoot = Join-Path $DataRoot 'browser\profiles'
    $profileExistsBefore = Test-Path -LiteralPath $profileRoot -PathType Container

    $sourceHashes = [ordered]@{
        'ChannelAgent.exe' = Get-Sha256 (Join-Path $packageRoot 'ChannelAgent.exe')
        'ui/channel-agent-avatar.png' = Get-Sha256 (Join-Path $packageRoot 'ui\channel-agent-avatar.png')
    }
    foreach ($relative in $allowedAssets) {
        $sourceHashes[$relative.Replace('\', '/')] = Get-Sha256 (Join-Path $packageRoot $relative)
    }

    $report = [ordered]@{
        schema_version = '1.0'
        operation = 'CHANNEL_AGENT_BRAND_ONLY_UPGRADE'
        source_archive = $PackageArchive
        source_archive_sha256 = $archiveSha
        branding_status = 'official'
        client_resource_version = '2.0.0rc2'
        agent_runtime_version_before = $stateBefore.agent_version
        agent_control_protocol = [string]$currentManifest.agent_control_protocol
        install_root = $InstallRoot
        data_root = $DataRoot
        validate_only = [bool]$ValidateOnly
        started_at = [DateTimeOffset]::UtcNow.ToString('o')
        before = $stateBefore
        protected_hashes_before = [ordered]@{
            config = $configShaBefore
            channel_agent_pyz = $pyzShaBefore
        }
        source_brand_hashes = $sourceHashes
        tray_pid_before = @($trayBefore | ForEach-Object { $_.ProcessId })
        edge_pids_before = $edgeBefore
        profile_root_existed_before = $profileExistsBefore
    }

    if ($ValidateOnly) {
        $report.result = 'VALIDATION_PASSED'
        $report.completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    } else {
        if (-not $PSCmdlet.ShouldProcess($InstallRoot, 'Apply ChannelAgent 2.0.0rc2 brand-only upgrade')) {
            throw 'Brand upgrade was not confirmed.'
        }

        foreach ($relative in $backupFiles) { Copy-BackupFile $relative $backupRoot }

        foreach ($tray in $trayBefore) {
            Stop-Process -Id $tray.ProcessId -Force
        }
        Start-Sleep -Milliseconds 500
        if ((Get-ProcessByExactPath (Join-Path $InstallRoot 'ChannelAgent.exe')).Count -ne 0) {
            throw 'The tray launcher did not exit; no files were replaced.'
        }
        if (-not (Test-ProcessId ([int]$stateBeforeRaw.pid))) {
            throw 'Agent Runtime stopped when only the tray should have exited.'
        }

        $exeTarget = Join-Path $InstallRoot 'ChannelAgent.exe'
        $exeStaged = Join-Path $InstallRoot 'ChannelAgent.exe.brand-new'
        Copy-Item -LiteralPath (Join-Path $packageRoot 'ChannelAgent.exe') -Destination $exeStaged -Force
        Move-Item -LiteralPath $exeStaged -Destination $exeTarget -Force

        foreach ($relative in $allowedAssets) {
            $target = Join-Path $InstallRoot $relative
            if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { [void]$createdPaths.Add($relative) }
            New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $packageRoot $relative) -Destination $target -Force
        }

        $avatarRelative = 'ui\channel-agent-avatar.png'
        $avatarTarget = Join-Path $InstallRoot $avatarRelative
        if (-not (Test-Path -LiteralPath $avatarTarget -PathType Leaf)) { [void]$createdPaths.Add($avatarRelative) }
        Copy-Item -LiteralPath (Join-Path $packageRoot $avatarRelative) -Destination $avatarTarget -Force

        $indexPath = Join-Path $InstallRoot 'ui\index.html'
        if (Test-Path -LiteralPath $indexPath -PathType Leaf) {
            $html = [System.IO.File]::ReadAllText($indexPath)
            $favicon = '<link rel="icon" type="image/png" href="/channel-agent-avatar.png" data-channel-agent-brand="2.0.0rc2">'
            if ($html -match 'data-channel-agent-brand="[^"]+"') {
                $html = [regex]::Replace(
                    $html,
                    '<link[^>]+data-channel-agent-brand="[^"]+"[^>]*>',
                    $favicon,
                    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
            } elseif ($html -match '</head>') {
                $headClose = [regex]::new(
                    '</head>',
                    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
                $html = $headClose.Replace($html, "$favicon</head>", 1)
            } else {
                throw 'Desktop Assistant index.html has no head element for the favicon.'
            }
            [System.IO.File]::WriteAllText($indexPath, $html, [System.Text.UTF8Encoding]::new($false))
        }

        $brandState = [ordered]@{
            schema_version = '1.0'
            client_resource_version = '2.0.0rc2'
            agent_runtime_version = $stateBefore.agent_version
            agent_control_protocol = [string]$currentManifest.agent_control_protocol
            source_archive_sha256 = $archiveSha
            branding_status = 'official'
            installed_at = [DateTimeOffset]::UtcNow.ToString('o')
            files = $sourceHashes
        }
        $brandState | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $InstallRoot 'brand-upgrade-manifest.json') -Encoding UTF8

        $shortcutName = Get-ChannelAgentShortcutName
        $desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) $shortcutName
        if (Test-Path -LiteralPath $desktopShortcut -PathType Leaf) {
            Copy-Item -LiteralPath $desktopShortcut -Destination (Join-Path $backupRoot $shortcutName) -Force
        }
        else {
            $shortcutCreated = $true
        }
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($desktopShortcut)
        $shortcut.TargetPath = $exeTarget
        $shortcut.WorkingDirectory = $InstallRoot
        $shortcut.IconLocation = "$exeTarget,0"
        $shortcut.Save()
        $iconRefresh = Join-Path $env:SystemRoot 'System32\ie4uinit.exe'
        if (Test-Path -LiteralPath $iconRefresh -PathType Leaf) {
            Start-Process -FilePath $iconRefresh -ArgumentList '-show' -WindowStyle Hidden -Wait
        }

        Start-Process -FilePath $exeTarget -WindowStyle Hidden
        $trayAfter = @()
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 250
            $trayAfter = @(Get-ProcessByExactPath $exeTarget)
            if ($trayAfter.Count -gt 0) { break }
        }
        if ($trayAfter.Count -eq 0) { throw 'The branded tray launcher did not start.' }
        if (-not (Test-ProcessId ([int]$stateBeforeRaw.pid))) {
            throw 'Agent Runtime PID changed or stopped during the tray restart.'
        }

        Start-Sleep -Seconds 1
        $stateAfterRaw = Read-AgentState
        $stateAfter = Get-SafeStateView $stateAfterRaw
        Assert-StateIdentityUnchanged $stateBeforeRaw $stateAfterRaw
        if ([int]$stateAfterRaw.pid -ne [int]$stateBeforeRaw.pid) {
            throw 'Agent Runtime PID changed during brand-only upgrade.'
        }
        if ((Get-Sha256 $configPath) -ne $configShaBefore) { throw 'Agent configuration changed.' }
        if ((Get-Sha256 $pyzPath) -ne $pyzShaBefore) { throw 'ChannelAgent runtime application changed.' }
        if ($profileExistsBefore -and -not (Test-Path -LiteralPath $profileRoot -PathType Container)) {
            throw 'Browser profile root disappeared during brand-only upgrade.'
        }
        foreach ($edgePid in $edgeBefore) {
            if (-not (Get-Process -Id $edgePid -ErrorAction SilentlyContinue)) {
                throw "An existing Edge process stopped during brand-only upgrade: $edgePid"
            }
        }

        $installedExe = Get-Item -LiteralPath $exeTarget
        if ($installedExe.VersionInfo.FileVersion -ne '2.0.0.2' -or $installedExe.VersionInfo.ProductVersion -ne '2.0.0rc2') {
            throw 'Installed executable version resources are incorrect.'
        }

        $upgradeApplied = $true
        $report.after = $stateAfter
        $report.agent_runtime_version_after = $stateAfter.agent_version
        $report.tray_pid_after = @($trayAfter | ForEach-Object { $_.ProcessId })
        $report.edge_pids_after = @(Get-Process -Name 'msedge' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
        $report.protected_hashes_after = [ordered]@{
            config = Get-Sha256 $configPath
            channel_agent_pyz = Get-Sha256 $pyzPath
        }
        $report.exe_version = [ordered]@{
            file_version = $installedExe.VersionInfo.FileVersion
            product_version = $installedExe.VersionInfo.ProductVersion
            sha256 = Get-Sha256 $exeTarget
        }
        $report.backup_root = $backupRoot
        $report.result = 'UPGRADE_PASSED'
        $report.completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
}
catch {
    if (-not $ValidateOnly -and (Test-Path -LiteralPath $backupRoot -PathType Container)) {
        $rollbackPerformed = $true
        foreach ($tray in @(Get-ProcessByExactPath (Join-Path $InstallRoot 'ChannelAgent.exe'))) {
            Stop-Process -Id $tray.ProcessId -Force -ErrorAction SilentlyContinue
        }
        foreach ($relative in $backupFiles) {
            Restore-BackupFile $relative $backupRoot
        }
        $shortcutName = Get-ChannelAgentShortcutName
        $shortcutBackup = Join-Path $backupRoot $shortcutName
        $desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) $shortcutName
        if (Test-Path -LiteralPath $shortcutBackup -PathType Leaf) {
            Copy-Item -LiteralPath $shortcutBackup -Destination $desktopShortcut -Force
        }
        elseif ($shortcutCreated -and (Test-Path -LiteralPath $desktopShortcut -PathType Leaf)) {
            Remove-Item -LiteralPath $desktopShortcut -Force
        }
        $oldExe = Join-Path $InstallRoot 'ChannelAgent.exe'
        if (Test-Path -LiteralPath $oldExe -PathType Leaf) {
            Start-Process -FilePath $oldExe -WindowStyle Hidden
        }
    }
    if ($report) {
        $report.result = 'UPGRADE_FAILED'
        $report.rollback_performed = $rollbackPerformed
        $report.error = $_.Exception.Message
        $report.completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    throw
}
finally {
    if ($ReportPath -and $report) {
        $resolvedReport = [System.IO.Path]::GetFullPath($ReportPath)
        New-Item -ItemType Directory -Path (Split-Path $resolvedReport -Parent) -Force | Out-Null
        $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resolvedReport -Encoding UTF8
    }
    if (Test-Path -LiteralPath $tempRoot -PathType Container) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

if ($report) {
    Write-Output "result=$($report.result)"
    Write-Output "client_resource_version=2.0.0rc2"
    Write-Output "agent_runtime_version=$($report.agent_runtime_version_before)"
    Write-Output "agent_control_protocol=$($report.agent_control_protocol)"
}
