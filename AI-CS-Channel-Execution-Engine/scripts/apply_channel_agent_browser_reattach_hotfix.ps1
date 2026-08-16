[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent'),
    [string]$FrontendBuild
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'windows\Resolve-AiCsRepositoryRoot.ps1')
$aiCsRoot = Resolve-AiCsRepositoryRoot $repoRoot
if ([string]::IsNullOrWhiteSpace($FrontendBuild)) {
    $FrontendBuild = Join-Path $aiCsRoot 'frontend\dist-agent'
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$FrontendBuild = [IO.Path]::GetFullPath($FrontendBuild)
$statePath = Join-Path $DataRoot 'runtime\channel-agent-state.json'
$runtimePath = Join-Path $InstallRoot 'app\channel-agent.pyz'
$executablePath = Join-Path $InstallRoot 'ChannelAgent.exe'
$uiRoot = Join-Path $InstallRoot 'ui'
$pendingRuntime = "$runtimePath.hotfix-pending"
$replacementStarted = $false
$backupRoot = $null

function Get-Json([string]$Path) {
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Wait-ProcessExit([int]$ProcessId, [int]$TimeoutSeconds) {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

try {
    foreach ($required in @(
        $statePath,
        $runtimePath,
        $executablePath,
        (Join-Path $FrontendBuild 'index.html'),
        (Join-Path $repoRoot 'src\channel_agent\browser.py'),
        (Join-Path $repoRoot 'src\channel_agent\pdd_login.py'),
        (Join-Path $repoRoot 'src\channel_agent\windows.py')
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Missing hotfix input: $required"
        }
    }

    $before = Get-Json $statePath
    $runtimePid = [int]$before.pid
    if (-not (Get-Process -Id $runtimePid -ErrorAction SilentlyContinue)) {
        throw 'Agent runtime is not running.'
    }
    $profilePath = [IO.Path]::GetFullPath(
        (Join-Path $DataRoot ([string]$before.browser_profile_reference).Replace('/', '\'))
    )
    $edgeCandidates = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($profilePath)
    })
    $edgeIds = @($edgeCandidates | Select-Object -ExpandProperty ProcessId)
    $mainEdge = $edgeCandidates |
        Where-Object { $_.ParentProcessId -notin $edgeIds } |
        Select-Object -First 1
    if (-not $mainEdge) { throw 'Dedicated Edge profile process was not found.' }
    $edgePid = [int]$mainEdge.ProcessId

    $stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $backupRoot = Join-Path $InstallRoot ".hotfix-backups\browser-reattach-$stamp"
    New-Item -ItemType Directory -Path (Join-Path $backupRoot 'ui') -Force | Out-Null
    Copy-Item -LiteralPath $runtimePath -Destination (Join-Path $backupRoot 'channel-agent.pyz') -Force
    Copy-Item -LiteralPath (Join-Path $uiRoot 'index.html') -Destination (Join-Path $backupRoot 'ui\index.html') -Force

    Copy-Item -LiteralPath $runtimePath -Destination $pendingRuntime -Force
    $archive = [IO.Compression.ZipFile]::Open(
        $pendingRuntime,
        [IO.Compression.ZipArchiveMode]::Update
    )
    try {
        foreach ($name in @('browser.py', 'pdd_login.py', 'windows.py')) {
            $entryName = "channel_agent/$name"
            $entry = $archive.GetEntry($entryName)
            if ($null -eq $entry) { throw "Missing runtime member: $entryName" }
            $entry.Delete()
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                (Join-Path $repoRoot "src\channel_agent\$name"),
                $entryName,
                [IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
    finally {
        $archive.Dispose()
    }
    $runtimeHashBefore = (Get-FileHash -LiteralPath $runtimePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $runtimeHashAfter = (Get-FileHash -LiteralPath $pendingRuntime -Algorithm SHA256).Hash.ToLowerInvariant()

    Get-CimInstance Win32_Process -Filter "Name='ChannelAgent.exe'" | Where-Object {
        $_.ExecutablePath -and
        [IO.Path]::GetFullPath($_.ExecutablePath).Equals(
            $executablePath,
            [StringComparison]::OrdinalIgnoreCase
        )
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

    $reloadPath = Join-Path $DataRoot 'runtime\reload.request'
    [IO.File]::WriteAllText(
        $reloadPath,
        '{"reason":"BROWSER_PROFILE_REATTACH_HOTFIX","preserve_browser":true}',
        [Text.UTF8Encoding]::new($false)
    )
    if (-not (Wait-ProcessExit $runtimePid 30)) {
        throw 'Old Agent runtime did not stop within 30 seconds.'
    }
    if (-not (Get-Process -Id $edgePid -ErrorAction SilentlyContinue)) {
        throw 'Dedicated Edge stopped during the controlled reload.'
    }

    Move-Item -LiteralPath $pendingRuntime -Destination $runtimePath -Force
    Copy-Item -LiteralPath (Join-Path $FrontendBuild 'index.html') -Destination (Join-Path $uiRoot 'index.html') -Force
    Copy-Item -Path (Join-Path $FrontendBuild 'assets\*') -Destination (Join-Path $uiRoot 'assets') -Force
    $replacementStarted = $true

    Start-Process -FilePath $executablePath -WindowStyle Hidden
    $after = $null
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(45)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        try {
            $candidate = Get-Json $statePath
            if (
                $candidate.pid -and
                [int]$candidate.pid -ne $runtimePid -and
                (Get-Process -Id ([int]$candidate.pid) -ErrorAction SilentlyContinue) -and
                $candidate.browser_pid
            ) {
                $after = $candidate
                break
            }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $after) { throw 'Hotfixed Agent did not restore the browser attachment.' }
    foreach ($field in @(
        'agent_id',
        'device_id',
        'identity_status',
        'binding_revision',
        'active_store_id',
        'browser_profile_reference'
    )) {
        if ([string]$after.$field -ne [string]$before.$field) {
            throw "Protected state changed: $field"
        }
    }
    if (-not (Get-Process -Id $edgePid -ErrorAction SilentlyContinue)) {
        throw 'Dedicated Edge process changed during the hotfix.'
    }

    [ordered]@{
        status = 'PASSED'
        previous_runtime_pid = $runtimePid
        runtime_pid = [int]$after.pid
        edge_pid = $edgePid
        browser_pid = [int]$after.browser_pid
        browser_status = [string]$after.browser_status
        pdd_login_state = [string]$after.pdd_login_state
        pdd_store_id = $after.pdd_store_id
        identity_status = [string]$after.identity_status
        binding_revision = [int]$after.binding_revision
        runtime_sha256_before = $runtimeHashBefore
        runtime_sha256_after = $runtimeHashAfter
        backup_root = $backupRoot
    } | ConvertTo-Json -Depth 4
}
catch {
    if ($replacementStarted -and $backupRoot) {
        Copy-Item -LiteralPath (Join-Path $backupRoot 'channel-agent.pyz') -Destination $runtimePath -Force
        Copy-Item -LiteralPath (Join-Path $backupRoot 'ui\index.html') -Destination (Join-Path $uiRoot 'index.html') -Force
    }
    if (-not (Get-CimInstance Win32_Process -Filter "Name='ChannelAgent.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath).Equals($executablePath, [StringComparison]::OrdinalIgnoreCase)
    })) {
        Start-Process -FilePath $executablePath -WindowStyle Hidden
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $pendingRuntime -PathType Leaf) {
        Remove-Item -LiteralPath $pendingRuntime -Force
    }
}
