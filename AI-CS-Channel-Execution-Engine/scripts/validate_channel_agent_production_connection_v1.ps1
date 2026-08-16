[CmdletBinding()]
param(
    [string]$ValidationRoot = (Join-Path $env:TEMP 'ai-cs-channel-agent-production-connection-v1'),
    [int]$Port = 18191,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$validationRoot = [System.IO.Path]::GetFullPath($ValidationRoot)
$installRoot = Join-Path $validationRoot 'install'
$dataRoot = Join-Path $validationRoot 'data'
$startupDirectory = Join-Path $validationRoot 'startup'
$database = Join-Path $validationRoot 'channel-engine.sqlite3'
$packageRoot = Join-Path $repoRoot 'dist\windows-client-v1\AI-CS-Channel-Agent'
$installer = Join-Path $packageRoot 'install\Install-AI-CS-Channel-Agent.ps1'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$serverScript = Join-Path $repoRoot 'tests\support\channel_agent_connection_validation_server.py'
$executable = Join-Path $installRoot 'ChannelAgent.exe'
$agentId = 'agent-production-connection-001'
$deviceId = 'device-production-connection-001'
$operatorHeaders = @{
    'X-Operator-Session-Reference' = 'channel-agent-validation-admin'
}
$serverProcess = $null
$result = [ordered]@{}

function Wait-ValidationCondition {
    param(
        [scriptblock]$Predicate,
        [string]$FailureMessage,
        [int]$TimeoutSeconds = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            if (& $Predicate) { return }
        } catch {
            # Transient connection and partially-written-state errors are expected while waiting.
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    throw $FailureMessage
}

function Get-ValidationListenerProcessId {
    $pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in (& netstat -ano -p TCP)) {
        if ($line -match $pattern) {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Start-ValidationServer {
    $launcherProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @($serverScript, '--database', $database, '--port', $Port) `
        -WorkingDirectory $repoRoot `
        -PassThru `
        -WindowStyle Hidden
    Wait-ValidationCondition `
        -TimeoutSeconds 90 `
        -FailureMessage 'Local validation server failed to start.' `
        -Predicate {
        try {
            Invoke-RestMethod `
                -Uri "http://127.0.0.1:$Port/channel-agent/v1/admin/agents" `
                -Headers $operatorHeaders `
                -TimeoutSec 1 | Out-Null
            return $true
        } catch {
            return $false
        }
    }
    $listenerProcessId = Get-ValidationListenerProcessId
    if ($null -eq $listenerProcessId) {
        throw 'Local validation server has no listening process.'
    }
    if ($listenerProcessId -eq $launcherProcess.Id) {
        return $launcherProcess
    }
    return Get-Process -Id $listenerProcessId -ErrorAction Stop
}

function Get-AgentState {
    $path = Join-Path $dataRoot 'runtime\channel-agent-state.json'
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-AdminAgent {
    return Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/channel-agent/v1/admin/agents/$agentId" `
        -Headers $operatorHeaders `
        -TimeoutSec 2
}

function Stop-ValidationServer {
    param([System.Diagnostics.Process]$Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        Wait-Process -Id $Process.Id -Timeout 5 -ErrorAction SilentlyContinue
        Wait-ValidationCondition `
            -FailureMessage 'Validation server port did not close.' `
            -Predicate { $null -eq (Get-ValidationListenerProcessId) }
    }
}

if (Test-Path -LiteralPath $validationRoot) {
    throw "ValidationRoot already exists and will not be overwritten: $validationRoot"
}
$probe = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    $Port
)
try {
    $probe.Start()
} catch {
    throw "Validation port is already in use: $Port"
} finally {
    $probe.Stop()
}

try {
    New-Item -ItemType Directory -Path $validationRoot, $startupDirectory -Force | Out-Null
    & $installer `
        -PackageRoot $packageRoot `
        -InstallRoot $installRoot `
        -DataRoot $dataRoot `
        -StartupDirectory $startupDirectory `
        -EnableAutoStart | Out-Null
    $result.install_exit = $LASTEXITCODE

    $validationConfig = [ordered]@{
        config_version = '1.0'
        server_url = "http://127.0.0.1:$Port"
        agent_id = $agentId
        device_id = $deviceId
        user_reference = $null
        store_reference = $null
        store_references = @()
        connect_timeout_seconds = 2.0
        heartbeat_interval_seconds = 0.1
        log_directory = (Join-Path $dataRoot 'logs')
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText(
        (Join-Path $dataRoot 'config\agent.json'),
        $validationConfig,
        [System.Text.UTF8Encoding]::new($false)
    )

    $serverProcess = Start-ValidationServer
    & $executable start --data-root $dataRoot --wait-seconds 10 | Out-Null
    $result.initial_start_exit = $LASTEXITCODE
    Wait-ValidationCondition -FailureMessage 'Initial Agent start failed.' -Predicate {
        (Get-AgentState).process_status -eq 'RUNNING'
    }
    $initialAdminState = Get-AdminAgent

    $grantBody = [ordered]@{
        agent_id = $agentId
        device_id = $deviceId
        user_reference = 'user-production-connection-001'
        store_references = @('store-production-a', 'store-production-b')
        reason = 'approved production connection validation'
    } | ConvertTo-Json
    $grant = Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:$Port/channel-agent/v1/admin/enrollment-grants" `
        -Headers $operatorHeaders `
        -ContentType 'application/json' `
        -Body $grantBody
    $grant.binding_code | & $executable enroll `
        --data-root $dataRoot `
        --binding-code-stdin | Out-Null
    $result.enroll_exit = $LASTEXITCODE
    if ($result.enroll_exit -ne 0) {
        throw "Agent enrollment failed with exit code $($result.enroll_exit)."
    }

    $activationBody = @{reason = 'binding verified for validation'} | ConvertTo-Json
    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:$Port/channel-agent/v1/admin/agents/$agentId/activate" `
        -Headers $operatorHeaders `
        -ContentType 'application/json' `
        -Body $activationBody | Out-Null
    Wait-ValidationCondition -FailureMessage 'Binding status did not synchronize.' -Predicate {
        $state = Get-AgentState
        $state.process_status -eq 'RUNNING' -and
            $state.identity_status -eq 'ACTIVE' -and
            @($state.store_ids).Count -eq 2
    }
    $boundState = Get-AgentState
    $onlineAdminState = Get-AdminAgent

    Stop-ValidationServer -Process $serverProcess
    $serverProcess = $null
    Wait-ValidationCondition -FailureMessage 'Agent did not enter DEGRADED after outage.' -Predicate {
        (Get-AgentState).process_status -eq 'DEGRADED'
    }
    $degradedState = Get-AgentState

    $serverProcess = Start-ValidationServer
    Wait-ValidationCondition -FailureMessage 'Agent did not recover after Engine restart.' -Predicate {
        (Get-AgentState).process_status -eq 'RUNNING'
    }
    Wait-ValidationCondition -FailureMessage 'Agent did not re-register after Engine restart.' -Predicate {
        (Get-AdminAgent).online_status -eq 'ONLINE'
    }
    $engineRecoveredState = Get-AgentState

    & $executable stop --data-root $dataRoot --wait-seconds 10 | Out-Null
    $result.stop_exit = $LASTEXITCODE
    Wait-ValidationCondition -FailureMessage 'OFFLINE status did not synchronize.' -Predicate {
        (Get-AdminAgent).online_status -eq 'OFFLINE'
    }
    $offlineAdminState = Get-AdminAgent

    & $executable start --data-root $dataRoot --wait-seconds 10 | Out-Null
    $result.restart_exit = $LASTEXITCODE
    Wait-ValidationCondition -FailureMessage 'Agent did not recover after local restart.' -Predicate {
        $state = Get-AgentState
        $state.process_status -eq 'RUNNING' -and $state.identity_status -eq 'ACTIVE'
    }
    $restartedState = Get-AgentState
    $binding = Get-Content `
        -LiteralPath (Join-Path $dataRoot 'runtime\agent-binding.json') `
        -Raw `
        -Encoding UTF8 | ConvertFrom-Json
    $sensitiveMatches = @(
        Get-ChildItem -LiteralPath $dataRoot -File -Recurse |
            Select-String `
                -Pattern 'binding_code|password|cookie|token' `
                -CaseSensitive:$false `
                -ErrorAction SilentlyContinue
    )

    $result.initial_online = $initialAdminState.online_status -eq 'ONLINE'
    $result.bound_user = $boundState.user_id -eq 'user-production-connection-001'
    $result.bound_store_count = @($boundState.store_ids).Count
    $result.admin_online = $onlineAdminState.online_status -eq 'ONLINE'
    $result.degraded_on_outage = $degradedState.process_status -eq 'DEGRADED'
    $result.engine_restart_recovered = $engineRecoveredState.process_status -eq 'RUNNING'
    $result.offline_after_stop = $offlineAdminState.online_status -eq 'OFFLINE'
    $result.agent_restart_recovered = $restartedState.process_status -eq 'RUNNING'
    $result.binding_persisted = (
        $binding.user_id -eq 'user-production-connection-001' -and
        @($binding.store_ids).Count -eq 2
    )
    $result.sensitive_matches = $sensitiveMatches.Count
    $result.client_version = (& $executable version | Select-Object -Last 1).Trim()
} finally {
    if (Test-Path -LiteralPath $executable -PathType Leaf) {
        & $executable stop --data-root $dataRoot --wait-seconds 3 2>$null | Out-Null
    }
    Stop-ValidationServer -Process $serverProcess
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $installRoot)) {
        & (Join-Path $installRoot 'install\Uninstall-AI-CS-Channel-Agent.ps1') `
            -InstallRoot $installRoot `
            -DataRoot $dataRoot `
            -StartupDirectory $startupDirectory `
            -RemoveData | Out-Null
    }
}

$result | ConvertTo-Json -Compress
