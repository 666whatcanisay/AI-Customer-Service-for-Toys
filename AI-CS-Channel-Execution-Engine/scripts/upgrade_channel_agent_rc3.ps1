[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$PackageArchive,
    [string]$InstallRoot = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent'),
    [string]$ExpectedArchiveSha256,
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
$PackageArchive = [System.IO.Path]::GetFullPath($PackageArchive)
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$expectedBaseline = 'a2f5f89f3656eeab2ad46deea39805de8d067e8978f5ee6f80e0f3839d75a31a'
$expectedGateway = 'e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-JsonWithRetry([string]$Path) {
    $last = $null
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch [System.UnauthorizedAccessException] { $last = $_.Exception }
        catch [System.IO.IOException] { $last = $_.Exception }
        if ($attempt -lt 7) { Start-Sleep -Milliseconds ([Math]::Min(20 * [Math]::Pow(2, $attempt), 250)) }
    }
    throw "Local state is temporarily unavailable: $Path ($($last.Message))"
}

function Get-ProfileIdentityFingerprint([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $null }
    $root = Get-Item -LiteralPath $Path
    $entries = [System.Collections.Generic.List[string]]::new()
    $entries.Add("root|$([System.IO.Path]::GetFullPath($root.FullName).ToLowerInvariant())|$($root.CreationTimeUtc.Ticks)")
    foreach ($relative in @('Local State', 'Default', 'Default\Network', 'Default\Sessions')) {
        $candidate = Join-Path $Path $relative
        if (-not (Test-Path -LiteralPath $candidate)) {
            $entries.Add("$($relative.Replace('\', '/'))|missing")
            continue
        }
        $item = Get-Item -LiteralPath $candidate
        $kind = $(if ($item.PSIsContainer) { 'directory' } else { 'file' })
        # Creation identity is stable while Edge writes normal session/metric data,
        # but changes when the profile is deleted, cleaned, or reinitialized.
        $entries.Add("$($relative.Replace('\', '/'))|$kind|$($item.CreationTimeUtc.Ticks)")
    }
    $payload = [System.Text.Encoding]::UTF8.GetBytes((@($entries) -join "`n"))
    $digest = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($digest.ComputeHash($payload))).Replace('-', '').ToLowerInvariant() }
    finally { $digest.Dispose() }
}

function Get-ExistingRelativeFiles([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return @() }
    return @(Get-ChildItem -LiteralPath $Path -Recurse -File | ForEach-Object {
        $_.FullName.Substring($Path.Length).TrimStart('\').Replace('\', '/')
    } | Sort-Object)
}

function Get-ExactProcess([string]$Name, [string]$ExecutablePath) {
    $expected = [System.IO.Path]::GetFullPath($ExecutablePath)
    return @(Get-CimInstance Win32_Process -Filter "Name='$Name'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
            $expected, [System.StringComparison]::OrdinalIgnoreCase
        )
    })
}

function Test-Process([int]$ProcessId) {
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Wait-ProcessExit([int]$ProcessId, [int]$Seconds) {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
    while ((Test-Process $ProcessId) -and [DateTimeOffset]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    return -not (Test-Process $ProcessId)
}

function Set-AtomicFile([string]$Source, [string]$Target) {
    $parent = Split-Path -Parent $Target
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $pending = "$Target.rc3-pending"
    $replaceBackup = "$Target.rc3-replace-backup"
    Copy-Item -LiteralPath $Source -Destination $pending -Force
    try {
        if (Test-Path -LiteralPath $Target -PathType Leaf) {
            # Windows PowerShell 5.1 coerces a null backup path to an empty string
            # for the four-argument overload. Use a real temporary backup path so
            # File.Replace remains atomic and receives only legal paths.
            [System.IO.File]::Replace($pending, $Target, $replaceBackup, $true)
        }
        else {
            Move-Item -LiteralPath $pending -Destination $Target
        }
    }
    finally {
        if (Test-Path -LiteralPath $pending -PathType Leaf) { Remove-Item -LiteralPath $pending -Force }
        if (Test-Path -LiteralPath $replaceBackup -PathType Leaf) { Remove-Item -LiteralPath $replaceBackup -Force }
    }
}

if (-not (Test-Path -LiteralPath $PackageArchive -PathType Leaf)) { throw 'RC3 package archive is missing.' }
if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) { throw 'ChannelAgent install root is missing.' }
if (-not (Test-Path -LiteralPath $DataRoot -PathType Container)) { throw 'ChannelAgent data root is missing.' }
$archiveSha = Get-Sha256 $PackageArchive
if ($ExpectedArchiveSha256 -and $archiveSha -ne $ExpectedArchiveSha256.ToLowerInvariant()) {
    throw 'RC3 package SHA256 does not match the approved value.'
}
if ((Get-Sha256 (Join-Path $InstallRoot 'app\channel-agent.pyz')) -ne $expectedBaseline) {
    throw 'Installed runtime is not the approved RC1 baseline; RC3 upgrade was not started.'
}

$temporaryRoot = Join-Path $env:TEMP ('channel-agent-rc3-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
$backupRoot = Join-Path $InstallRoot ('.rc3-upgrade-backups\' + [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$upgraded = $false
$rolledBack = $false
$createdTargets = [System.Collections.Generic.List[string]]::new()
$correctShortcutExisted = $false
$archivedMojibakeShortcuts = [System.Collections.Generic.List[object]]::new()
$report = [ordered]@{
    schema_version = '1.0'
    target_version = '2.0.0rc3'
    archive_sha256 = $archiveSha
    started_at = [DateTimeOffset]::UtcNow.ToString('o')
    status = 'STARTED'
    rollback_performed = $false
}

try {
    Expand-Archive -LiteralPath $PackageArchive -DestinationPath $temporaryRoot
    $packageRoot = Join-Path $temporaryRoot 'AI-CS-Channel-Agent'
    $manifestPath = Join-Path $packageRoot 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'RC3 package manifest is missing.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.version -ne '2.0.0rc3' -or $manifest.agent_runtime_version -ne '2.0.0rc3') {
        throw 'Package is not the approved ChannelAgent 2.0.0rc3 runtime.'
    }
    if ($manifest.agent_control_protocol -ne '2.1' -or $manifest.gateway_contract_sha256 -ne $expectedGateway) {
        throw 'RC3 package changes a frozen protocol or Gateway Contract.'
    }
    if ($manifest.runtime_baseline_sha256 -ne $expectedBaseline) { throw 'RC3 runtime baseline evidence is invalid.' }
    foreach ($file in $manifest.files) {
        $path = Join-Path $packageRoot ([string]$file.path).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Sha256 $path) -ne [string]$file.sha256) {
            throw "RC3 package file validation failed: $($file.path)"
        }
    }

    $statePath = Join-Path $DataRoot 'runtime\channel-agent-state.json'
    $bindingPath = Join-Path $DataRoot 'runtime\agent-binding.json'
    $configPath = Join-Path $DataRoot 'config\agent.json'
    $stateBefore = Get-JsonWithRetry $statePath
    $bindingBefore = Get-JsonWithRetry $bindingPath
    $configBefore = Get-JsonWithRetry $configPath
    if ([string]$configBefore.control_protocol_version -ne '2.1') { throw 'Installed Agent Control protocol is not 2.1.' }
    $profileRoot = Join-Path $DataRoot ([string]$stateBefore.browser_profile_reference).Replace('/', '\')
    if (-not $stateBefore.browser_profile_reference) { throw 'Browser Profile reference is missing.' }
    $pddSessionRoot = Join-Path $DataRoot 'runtime\pdd-login'
    $protectedFiles = @(
        'config\agent.json', 'runtime\agent-binding.json', 'runtime\bootstrap-device.json'
    )
    $protectedHashes = [ordered]@{}
    foreach ($relative in $protectedFiles) {
        $path = Join-Path $DataRoot $relative
        $protectedHashes[$relative] = $(if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Sha256 $path } else { $null })
    }
    $cursorHashes = [ordered]@{}
    # Cursor/spool protection is restricted to Agent-owned runtime/event data.
    # Scanning browser profiles would match unrelated names such as
    # DashTrackerDatabase (contains "ack") and can hit Edge-exclusive locks.
    foreach ($ownedRoot in @((Join-Path $DataRoot 'runtime'), (Join-Path $DataRoot 'events'))) {
        if (-not (Test-Path -LiteralPath $ownedRoot -PathType Container)) { continue }
        Get-ChildItem -LiteralPath $ownedRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match '(^|[-_.])(cursor|spool|ack|observation)([-_.]|$)'
        } | ForEach-Object { $cursorHashes[$_.FullName] = Get-Sha256 $_.FullName }
    }
    $profileFingerprintBefore = Get-ProfileIdentityFingerprint $profileRoot
    $pddFilesBefore = Get-ExistingRelativeFiles $pddSessionRoot
    $managedEdgePid = [int]$(if ($stateBefore.browser_pid) { $stateBefore.browser_pid } else { 0 })
    if ($managedEdgePid -gt 0 -and -not (Test-Process $managedEdgePid)) { throw 'Recorded managed Edge PID is not running.' }
    $runtimePid = [int]$stateBefore.pid
    if ($runtimePid -le 0 -or -not (Test-Process $runtimePid)) { throw 'ChannelAgent Runtime is not running.' }
    $runtimeProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$runtimePid"
    if (-not $runtimeProcess.CommandLine.Contains((Join-Path $InstallRoot 'app\channel-agent.pyz'))) {
        throw 'Running Runtime does not use the approved install root.'
    }
    $exeTarget = Join-Path $InstallRoot 'ChannelAgent.exe'
    $trayProcesses = Get-ExactProcess 'ChannelAgent.exe' $exeTarget
    $report.before = [ordered]@{
        runtime_pid = $runtimePid
        tray_pids = @($trayProcesses.ProcessId)
        agent_version = [string]$stateBefore.agent_version
        agent_id = [string]$stateBefore.agent_id
        device_id = [string]$stateBefore.device_id
        identity_status = [string]$stateBefore.identity_status
        binding_revision = [int]$stateBefore.binding_revision
        authorized_store_ids = @($stateBefore.authorized_store_ids)
        active_store_id = $stateBefore.active_store_id
        host_control_url = [string]$configBefore.server_url
        control_protocol = [string]$configBefore.control_protocol_version
        credential_reference = [string]$configBefore.device_credential_reference
        last_heartbeat = [string]$stateBefore.last_heartbeat
        browser_pid = $managedEdgePid
        browser_profile_reference = [string]$stateBefore.browser_profile_reference
        browser_profile_identity_sha256 = $profileFingerprintBefore
        pdd_login_state = [string]$stateBefore.pdd_login_state
        pdd_session_file_count = @($pddFilesBefore).Count
    }

    if (-not $PSCmdlet.ShouldProcess($InstallRoot, 'Apply controlled ChannelAgent 2.0.0rc3 runtime upgrade')) {
        $report.status = 'VALIDATED_ONLY'
        return
    }

    foreach ($process in $trayProcesses) { Stop-Process -Id $process.ProcessId -Force }
    $reloadPath = Join-Path $DataRoot 'runtime\reload.request'
    [System.IO.File]::WriteAllText(
        $reloadPath,
        '{"reason":"RC3_CONTROLLED_UPGRADE","preserve_browser":true}',
        [System.Text.UTF8Encoding]::new($false)
    )
    if (-not (Wait-ProcessExit $runtimePid 30)) { throw 'RC1 Runtime did not stop within the controlled reload window.' }
    if ($managedEdgePid -gt 0 -and -not (Test-Process $managedEdgePid)) { throw 'Managed Edge stopped during RC3 reload.' }

    $filesToReplace = @(
        'ChannelAgent.exe',
        'app\channel-agent.pyz',
        'release-manifest.json',
        'install\Install-AI-CS-Channel-Agent.ps1',
        'install\Uninstall-AI-CS-Channel-Agent.ps1',
        'install\ChannelAgentShortcutName.ps1',
        'install\Upgrade-ChannelAgent-RC3.ps1'
    )
    foreach ($relative in $filesToReplace) {
        $source = Join-Path $packageRoot $relative
        $target = Join-Path $InstallRoot $relative
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $backup = Join-Path $backupRoot $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
            Copy-Item -LiteralPath $target -Destination $backup -Force
        }
        else {
            [void]$createdTargets.Add($target)
        }
        Set-AtomicFile $source $target
    }

    $shortcutHelper = Join-Path $InstallRoot 'install\ChannelAgentShortcutName.ps1'
    . $shortcutHelper
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutName = Get-ChannelAgentShortcutName
    $correctShortcut = Join-Path $desktop $shortcutName
    if (Test-Path -LiteralPath $correctShortcut -PathType Leaf) {
        $correctShortcutExisted = $true
        Copy-Item -LiteralPath $correctShortcut -Destination (Join-Path $backupRoot $shortcutName) -Force
    }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($knownName in Get-ChannelAgentKnownMojibakeShortcutNames) {
        $candidate = Join-Path $desktop $knownName
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $shortcut = $shell.CreateShortcut($candidate)
        if ($shortcut.TargetPath -and [System.IO.Path]::GetFullPath($shortcut.TargetPath).Equals(
            $exeTarget, [System.StringComparison]::OrdinalIgnoreCase
        )) {
            $archivedPath = Join-Path $backupRoot $knownName
            Move-Item -LiteralPath $candidate -Destination $archivedPath -Force
            $archivedMojibakeShortcuts.Add([pscustomobject]@{
                original = $candidate
                backup = $archivedPath
            })
        }
    }
    $shortcut = $shell.CreateShortcut($correctShortcut)
    $shortcut.TargetPath = $exeTarget
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = 'AI-CS Channel Agent customer desktop client'
    $shortcut.IconLocation = "$exeTarget,0"
    $shortcut.Save()

    Start-Process -FilePath $exeTarget -WindowStyle Hidden
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    $stateAfter = $null
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        try {
            $candidate = Get-JsonWithRetry $statePath
            if (
                $candidate.agent_version -eq '2.0.0rc3' -and
                $candidate.pid -and
                (Test-Process ([int]$candidate.pid)) -and
                $candidate.runtime_status -eq 'ONLINE' -and
                -not [string]::IsNullOrWhiteSpace([string]$candidate.last_heartbeat) -and
                $candidate.last_heartbeat -ne $stateBefore.last_heartbeat
            ) {
                $stateAfter = $candidate
                break
            }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $stateAfter) { throw 'RC3 Runtime did not restore Host Control heartbeat within 60 seconds.' }

    foreach ($field in @('agent_id', 'device_id', 'identity_status', 'binding_revision', 'active_store_id', 'browser_profile_reference')) {
        if ([string]$stateAfter.$field -ne [string]$stateBefore.$field) { throw "Protected state changed: $field" }
    }
    if ((@($stateAfter.authorized_store_ids) -join '|') -ne (@($stateBefore.authorized_store_ids) -join '|')) {
        throw 'Authorized store bindings changed during RC3 upgrade.'
    }
    $configAfter = Get-JsonWithRetry $configPath
    foreach ($field in @('server_url', 'control_protocol_version', 'device_credential_reference')) {
        if ([string]$configAfter.$field -ne [string]$configBefore.$field) { throw "Host Control configuration changed: $field" }
    }
    foreach ($relative in $protectedFiles) {
        $path = Join-Path $DataRoot $relative
        $afterHash = $(if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Sha256 $path } else { $null })
        if ($afterHash -ne $protectedHashes[$relative]) { throw "Protected data file changed: $relative" }
    }
    foreach ($entry in $cursorHashes.GetEnumerator()) {
        if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf) -or (Get-Sha256 $entry.Key) -ne $entry.Value) {
            throw "Cursor or short-cache file changed: $($entry.Key)"
        }
    }
    if ((Get-ProfileIdentityFingerprint $profileRoot) -ne $profileFingerprintBefore) {
        throw 'Edge/PDD Profile was removed, cleaned, or reinitialized during RC3 upgrade.'
    }
    $pddFilesAfter = Get-ExistingRelativeFiles $pddSessionRoot
    foreach ($relative in $pddFilesBefore) {
        if ($relative -notin $pddFilesAfter) { throw "PDD Session file was removed: $relative" }
    }
    if ($managedEdgePid -gt 0 -and -not (Test-Process $managedEdgePid)) { throw 'Managed Edge PID changed during RC3 upgrade.' }

    $installedExe = Get-Item -LiteralPath $exeTarget
    if ($installedExe.VersionInfo.FileVersion -ne '2.0.0.3' -or $installedExe.VersionInfo.ProductVersion -ne '2.0.0rc3') {
        throw 'Installed RC3 executable version resource is invalid.'
    }
    $report.after = [ordered]@{
        runtime_pid = [int]$stateAfter.pid
        agent_version = [string]$stateAfter.agent_version
        client_version = [string]$stateAfter.client_version
        agent_id = [string]$stateAfter.agent_id
        device_id = [string]$stateAfter.device_id
        identity_status = [string]$stateAfter.identity_status
        binding_revision = [int]$stateAfter.binding_revision
        authorized_store_ids = @($stateAfter.authorized_store_ids)
        active_store_id = $stateAfter.active_store_id
        host_control_url = [string]$configAfter.server_url
        control_protocol = [string]$configAfter.control_protocol_version
        last_heartbeat = [string]$stateAfter.last_heartbeat
        browser_pid = $(if ($stateAfter.browser_pid) { [int]$stateAfter.browser_pid } else { 0 })
        browser_profile_reference = [string]$stateAfter.browser_profile_reference
        browser_profile_identity_sha256 = Get-ProfileIdentityFingerprint $profileRoot
        pdd_login_state = [string]$stateAfter.pdd_login_state
        pdd_session_file_count = @($pddFilesAfter).Count
        executable_file_version = [string]$installedExe.VersionInfo.FileVersion
        executable_product_version = [string]$installedExe.VersionInfo.ProductVersion
        runtime_sha256 = Get-Sha256 (Join-Path $InstallRoot 'app\channel-agent.pyz')
    }
    $report.status = 'PASSED'
    $upgraded = $true
}
catch {
    $report.status = 'FAILED'
    $report.error = $_.Exception.Message
    try {
        $exeTarget = Join-Path $InstallRoot 'ChannelAgent.exe'
        foreach ($process in Get-ExactProcess 'ChannelAgent.exe' $exeTarget) { Stop-Process -Id $process.ProcessId -Force }
        $currentState = Get-JsonWithRetry (Join-Path $DataRoot 'runtime\channel-agent-state.json')
        if ($currentState.pid -and (Test-Process ([int]$currentState.pid))) {
            [System.IO.File]::WriteAllText(
                (Join-Path $DataRoot 'runtime\reload.request'),
                '{"reason":"RC3_ROLLBACK","preserve_browser":true}',
                [System.Text.UTF8Encoding]::new($false)
            )
            if (-not (Wait-ProcessExit ([int]$currentState.pid) 30)) { throw 'RC3 rollback could not stop the patched Runtime.' }
        }
        foreach ($backup in Get-ChildItem -LiteralPath $backupRoot -Recurse -File -ErrorAction SilentlyContinue) {
            $relative = $backup.FullName.Substring($backupRoot.Length).TrimStart('\')
            if ($relative.EndsWith('.lnk', [System.StringComparison]::OrdinalIgnoreCase)) { continue }
            Set-AtomicFile $backup.FullName (Join-Path $InstallRoot $relative)
        }
        foreach ($created in $createdTargets) {
            if ((Test-Path -LiteralPath $created -PathType Leaf) -and $created.StartsWith(
                ($InstallRoot.TrimEnd('\') + '\'), [System.StringComparison]::OrdinalIgnoreCase
            )) {
                Remove-Item -LiteralPath $created -Force
            }
        }
        $helper = Join-Path $InstallRoot 'install\ChannelAgentShortcutName.ps1'
        if (Test-Path -LiteralPath $helper) {
            . $helper
            $correctShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) (Get-ChannelAgentShortcutName)
            $shortcutBackup = Join-Path $backupRoot (Get-ChannelAgentShortcutName)
            if (Test-Path -LiteralPath $shortcutBackup -PathType Leaf) {
                Copy-Item -LiteralPath $shortcutBackup -Destination $correctShortcut -Force
            }
            elseif (-not $correctShortcutExisted -and (Test-Path -LiteralPath $correctShortcut -PathType Leaf)) {
                Remove-Item -LiteralPath $correctShortcut -Force
            }
            foreach ($archivedShortcut in $archivedMojibakeShortcuts) {
                if (Test-Path -LiteralPath $archivedShortcut.backup -PathType Leaf) {
                    Move-Item -LiteralPath $archivedShortcut.backup -Destination $archivedShortcut.original -Force
                }
            }
        }
        Start-Process -FilePath $exeTarget -WindowStyle Hidden
        $rolledBack = $true
        $report.rollback_performed = $true
    }
    catch {
        $report.rollback_error = $_.Exception.Message
    }
    throw
}
finally {
    $report.completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    $report.backup_root = $backupRoot
    if (-not $ReportPath) {
        $ReportPath = Join-Path $InstallRoot 'logs\channel-agent-rc3-upgrade-report.json'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $ReportPath) -Force | Out-Null
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
    if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
    Write-Output "status=$($report.status)"
    Write-Output "report=$ReportPath"
    Write-Output "backup=$backupRoot"
    Write-Output "rollback=$rolledBack"
}
