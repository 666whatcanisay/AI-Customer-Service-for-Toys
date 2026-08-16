[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$statePath = Join-Path $DataRoot 'runtime\channel-agent-state.json'
$runtimeStatePath = Join-Path $DataRoot 'runtime\desktop-assistant.json'
$runtimePath = Join-Path $InstallRoot 'app\channel-agent.pyz'
$executablePath = Join-Path $InstallRoot 'ChannelAgent.exe'
$pendingRuntime = "$runtimePath.desktop-reload-pending"
$handoffPath = Join-Path $DataRoot 'runtime\desktop-bootstrap-handoff.json'
$reloadPath = Join-Path $DataRoot 'runtime\reload.request'
$restartPath = Join-Path $DataRoot 'runtime\restart-agent.request'
$backupRoot = $null
$replacementStarted = $false

function Get-Json([string]$Path) {
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
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
        $runtimeStatePath,
        $runtimePath,
        $executablePath,
        (Join-Path $repoRoot 'src\channel_agent\desktop.py'),
        (Join-Path $repoRoot 'src\channel_agent\diagnostics.py'),
        (Join-Path $repoRoot 'src\channel_agent\windows.py')
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Missing desktop reload hotfix input: $required"
        }
    }

    $before = Get-Json $statePath
    $runtimePid = [int]$before.pid
    if (-not (Get-Process -Id $runtimePid -ErrorAction SilentlyContinue)) {
        throw 'Agent Runtime is not running.'
    }
    $assistantProfile = [IO.Path]::GetFullPath(
        (Join-Path $DataRoot 'browser\assistant-ui')
    )
    $edgeCandidates = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($assistantProfile)
    })
    $edgeIds = @($edgeCandidates | Select-Object -ExpandProperty ProcessId)
    $mainEdges = @($edgeCandidates | Where-Object { $_.ParentProcessId -notin $edgeIds })
    if ($mainEdges.Count -ne 1) {
        throw "Expected exactly one green assistant Edge root; found $($mainEdges.Count)."
    }
    $mainEdge = $mainEdges[0]
    $edgePid = [int]$mainEdge.ProcessId
    $bootstrapMatch = [regex]::Match(
        [string]$mainEdge.CommandLine,
        '(?:[?&])bootstrap=([A-Za-z0-9_-]{20,128})'
    )
    if (-not $bootstrapMatch.Success) {
        throw 'The green assistant Edge URL has no valid bootstrap nonce.'
    }
    $oldBootstrap = $bootstrapMatch.Groups[1].Value

    $stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')
    $backupRoot = Join-Path $InstallRoot ".hotfix-backups\desktop-reload-$stamp"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Copy-Item -LiteralPath $runtimePath -Destination (Join-Path $backupRoot 'channel-agent.pyz') -Force
    Copy-Item -LiteralPath $statePath -Destination (Join-Path $backupRoot 'channel-agent-state.json') -Force
    Copy-Item -LiteralPath $runtimeStatePath -Destination (Join-Path $backupRoot 'desktop-assistant.json') -Force

    Copy-Item -LiteralPath $runtimePath -Destination $pendingRuntime -Force
    $archive = [IO.Compression.ZipFile]::Open(
        $pendingRuntime,
        [IO.Compression.ZipArchiveMode]::Update
    )
    try {
        foreach ($name in @('desktop.py', 'diagnostics.py', 'windows.py')) {
            $entryName = "channel_agent/$name"
            $entry = $archive.GetEntry($entryName)
            if ($null -eq $entry) { throw "Missing Runtime member: $entryName" }
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
    [IO.File]::WriteAllText(
        $handoffPath,
        (([ordered]@{
            schema_version = 'channel-agent-desktop-bootstrap-handoff.v1'
            bootstrap_nonce = $oldBootstrap
            issued_at = [DateTimeOffset]::UtcNow.ToString('o')
        } | ConvertTo-Json -Compress) + "`n"),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $reloadPath,
        '{"schema_version":"channel-agent-reload.v1","reason":"RC5_DESKTOP_SESSION_HANDOFF_HOTFIX","preserve_browser":true}',
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $restartPath,
        "restart-preserve-assistant`n",
        [Text.UTF8Encoding]::new($false)
    )

    if (-not (Wait-ProcessExit $runtimePid 30)) {
        throw 'Old Agent Runtime did not stop within 30 seconds.'
    }
    if (-not (Get-Process -Id $edgePid -ErrorAction SilentlyContinue)) {
        throw 'Green assistant Edge stopped during controlled reload.'
    }

    Move-Item -LiteralPath $pendingRuntime -Destination $runtimePath -Force
    $replacementStarted = $true

    $after = $null
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        try {
            $candidate = Get-Json $statePath
            if (
                $candidate.pid -and
                [int]$candidate.pid -ne $runtimePid -and
                (Get-Process -Id ([int]$candidate.pid) -ErrorAction SilentlyContinue) -and
                [string]$candidate.runtime_status -eq 'ONLINE'
            ) {
                $after = $candidate
                break
            }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $after) { throw 'Hotfixed Agent Runtime did not recover within 60 seconds.' }
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
        throw 'Green assistant Edge process changed during hotfix.'
    }

    [ordered]@{
        status = 'PASSED'
        previous_runtime_pid = $runtimePid
        runtime_pid = [int]$after.pid
        edge_pid = $edgePid
        edge_preserved = $true
        agent_id = [string]$after.agent_id
        device_id = [string]$after.device_id
        binding_revision = [int]$after.binding_revision
        browser_profile_reference = [string]$after.browser_profile_reference
        runtime_sha256_before = $runtimeHashBefore
        runtime_sha256_after = $runtimeHashAfter
        backup_root = $backupRoot
        old_bootstrap_handoff_created = $true
    } | ConvertTo-Json -Depth 4
}
catch {
    if ($replacementStarted -and $backupRoot) {
        Copy-Item -LiteralPath (Join-Path $backupRoot 'channel-agent.pyz') -Destination $runtimePath -Force
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $pendingRuntime -PathType Leaf) {
        Remove-Item -LiteralPath $pendingRuntime -Force
    }
}
