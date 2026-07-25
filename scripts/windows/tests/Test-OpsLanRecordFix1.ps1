Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-lan-record-fix1-' + [Guid]::NewGuid().ToString('N'))
$script:fakeProcesses = @()
$script:detachedListenerPids = @()

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
    } catch {
        return
    }
    throw "$Label should fail but did not."
}

function Assert-Equal($Actual, $Expected, [string]$Label) {
    if ($Actual -ne $Expected) { throw "$Label expected '$Expected' but got '$Actual'." }
}

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Start-TestManagedService([hashtable]$Config, [string]$ServiceName, [int]$Port, [hashtable]$Environment, [string]$ShellPath, [string]$WorkingDirectory) {
    $listenerCommand = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $Port + '); $listener.Start(); Start-Sleep -Seconds 90'
    $process = Start-ManagedServiceWithEnvironment -Config $Config -Name $ServiceName -ExecutablePath $ShellPath -Arguments @('-NoProfile', '-Command', $listenerCommand) -WorkingDirectory $WorkingDirectory -CommandFeature 'TcpListener' -Port $Port -Environment $Environment
    $script:fakeProcesses += $process
    Start-Sleep -Milliseconds 300
    Update-ManagedServiceListenerRecord $Config $ServiceName | Out-Null
    return $process
}

try {
    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $runtimeDirectory = Join-Path $temporaryRoot 'runtime'
    $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $config = @{ RuntimeDirectory = $runtimeDirectory }

    $environmentNames = @('DATABASE_URL', 'CORS_ALLOWED_ORIGINS', 'LLM_PROVIDER', 'LLM_MODEL', 'VITE_RAG_API_BASE_URL', 'VITE_PLATFORM_API_BASE_URL')
    $environmentBefore = @{}
    foreach ($environmentVariableName in $environmentNames) {
        $environmentBefore[$environmentVariableName] = [Environment]::GetEnvironmentVariable($environmentVariableName, 'Process')
    }

    try {
        [Environment]::SetEnvironmentVariable('DATABASE_URL', 'before-database', 'Process')
        [Environment]::SetEnvironmentVariable('LLM_MODEL', $null, 'Process')
        Invoke-WithProcessEnvironment -Environment @{ DATABASE_URL='inside-database'; LLM_MODEL='inside-model' } -Action {
            Assert-Equal ([Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')) 'inside-database' 'Environment normal action database value'
            Assert-Equal ([Environment]::GetEnvironmentVariable('LLM_MODEL', 'Process')) 'inside-model' 'Environment normal action model value'
        }
        Assert-Equal ([Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')) 'before-database' 'Environment normal action restoration'
        if ($null -ne [Environment]::GetEnvironmentVariable('LLM_MODEL', 'Process')) { throw 'Environment normal action did not restore an absent variable.' }

        Assert-Throws {
            Invoke-WithProcessEnvironment -Environment @{ DATABASE_URL='throw-database'; LLM_MODEL='throw-model' } -Action { throw 'expected action failure' }
        } 'Environment throwing action'
        Assert-Equal ([Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')) 'before-database' 'Environment throwing action restoration'
        if ($null -ne [Environment]::GetEnvironmentVariable('LLM_MODEL', 'Process')) { throw 'Environment throwing action did not restore an absent variable.' }
    } finally {
        foreach ($environmentVariableName in $environmentNames) {
            [Environment]::SetEnvironmentVariable($environmentVariableName, $environmentBefore[$environmentVariableName], 'Process')
        }
    }

    $serviceDefinitions = @(
        @{ ServiceName='platform'; Port=(Get-AvailableLoopbackPort); Environment=@{ DATABASE_URL='sqlite:///lan-test.db'; CORS_ALLOWED_ORIGINS='http://192.168.1.20:5173' } },
        @{ ServiceName='rag'; Port=(Get-AvailableLoopbackPort); Environment=@{ CORS_ALLOWED_ORIGINS='http://192.168.1.20:5173'; LLM_PROVIDER='ollama'; LLM_MODEL='qwen3.5:9b' } },
        @{ ServiceName='customer-web'; Port=(Get-AvailableLoopbackPort); Environment=@{ VITE_RAG_API_BASE_URL='http://192.168.1.20:8000'; VITE_PLATFORM_API_BASE_URL='http://192.168.1.20:8011' } }
    )
    $started = @{}
    foreach ($definition in $serviceDefinitions) {
        $process = Start-TestManagedService $config $definition.ServiceName $definition.Port $definition.Environment $shellPath $temporaryRoot
        $started[$definition.ServiceName] = $process
        $recordPath = Get-ServiceRecordPath $config $definition.ServiceName
        if (-not (Test-Path -LiteralPath $recordPath)) { throw "Missing $($definition.ServiceName).json." }
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Equal $record.name $definition.ServiceName "$($definition.ServiceName) record name"
        Assert-Equal ([int]$record.pid) $process.Id "$($definition.ServiceName) record pid"
        Assert-Equal ([int]$record.port) $definition.Port "$($definition.ServiceName) record port"
        Assert-Equal ([IO.Path]::GetFullPath($record.executablePath)) ([IO.Path]::GetFullPath($shellPath)) "$($definition.ServiceName) executable path"
        Assert-Equal ([IO.Path]::GetFullPath($record.workingDirectory)) ([IO.Path]::GetFullPath($temporaryRoot)) "$($definition.ServiceName) working directory"
        Assert-Equal $record.commandFeature 'TcpListener' "$($definition.ServiceName) command feature"
        Assert-Equal ([int]$record.managed_pid) $process.Id "$($definition.ServiceName) managed pid"
        Assert-Equal ([int]$record.listener_pid) $process.Id "$($definition.ServiceName) listener pid"
        if ([string]::IsNullOrWhiteSpace([string]$record.listener_executable_path) -or [string]::IsNullOrWhiteSpace([string]$record.listener_started_at)) { throw "$($definition.ServiceName) listener identity fields are incomplete." }
        $status = Get-ServiceStatus $config $definition.ServiceName $definition.Port 'http://127.0.0.1:1'
        if (-not $status.Record.Valid) { throw "$($definition.ServiceName) managed status did not accept its valid record." }
        Assert-Equal ([int]$status.ProcessId) $process.Id "$($definition.ServiceName) managed status pid"
        Assert-Equal ([int]$status.ListenerProcessId) $process.Id "$($definition.ServiceName) listener status pid"
    }

    $expectedRecordFiles = @('customer-web.json', 'platform.json', 'rag.json')
    $actualRecordFiles = @(Get-ChildItem -LiteralPath $runtimeDirectory -File -Filter '*.json' | Select-Object -ExpandProperty Name | Sort-Object)
    if ((Compare-Object -ReferenceObject $expectedRecordFiles -DifferenceObject $actualRecordFiles)) { throw "Unexpected runtime records: $($actualRecordFiles -join ', ')" }
    foreach ($environmentVariableName in $environmentNames) {
        if (Test-Path -LiteralPath (Join-Path $runtimeDirectory "$environmentVariableName.json")) { throw "Environment variable leaked into a record filename: $environmentVariableName.json" }
    }

    # Windows launchers may exit after creating the actual listener. The record
    # must retain both identities and stop only the verified listener when its
    # original wrapper has already exited.
    $detachedPort = Get-AvailableLoopbackPort
    $listenerScriptPath = Join-Path $temporaryRoot 'listener-wrapper.ps1'
    @"
`$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $detachedPort)
`$listener.Start()
Start-Sleep -Seconds 90
"@ | Set-Content -LiteralPath $listenerScriptPath -Encoding UTF8
    $escapedShellPath = $shellPath.Replace("'", "''")
    $escapedListenerScriptPath = $listenerScriptPath.Replace("'", "''")
    $wrapperCommand = "Start-Process -FilePath '$escapedShellPath' -ArgumentList @('-NoProfile','-File','$escapedListenerScriptPath') -WindowStyle Hidden; Start-Sleep -Milliseconds 300"
    $detachedWrapper = Start-ManagedServiceWithEnvironment -Config $config -Name 'detached-wrapper' -ExecutablePath $shellPath -Arguments @('-NoProfile','-Command',$wrapperCommand) -WorkingDirectory $temporaryRoot -CommandFeature 'listener-wrapper.ps1' -Port $detachedPort -Environment @{}
    $script:fakeProcesses += $detachedWrapper
    for ($attempt = 0; $attempt -lt 30 -and @(Get-PortOwner $detachedPort).Count -ne 1; $attempt++) { Start-Sleep -Milliseconds 100 }
    Update-ManagedServiceListenerRecord $config 'detached-wrapper' | Out-Null
    for ($attempt = 0; $attempt -lt 30 -and (Get-Process -Id $detachedWrapper.Id -ErrorAction SilentlyContinue); $attempt++) { Start-Sleep -Milliseconds 100 }
    $detachedRecordPath = Get-ServiceRecordPath $config 'detached-wrapper'
    $detachedRecord = Get-Content -LiteralPath $detachedRecordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ((Get-Process -Id $detachedWrapper.Id -ErrorAction SilentlyContinue)) { throw 'Detached listener wrapper did not exit.' }
    if ([int]$detachedRecord.managed_pid -ne $detachedWrapper.Id -or [int]$detachedRecord.listener_pid -eq $detachedWrapper.Id) { throw 'Detached listener record did not preserve separate managed and listener PIDs.' }
    $script:detachedListenerPids += [int]$detachedRecord.listener_pid
    $detachedCheck = Test-RecordedProcess $config 'detached-wrapper'
    if (-not $detachedCheck.Valid -or $detachedCheck.Process -or -not $detachedCheck.ListenerProcess) { throw "Detached listener record was not safely accepted: $($detachedCheck.Reason)" }
    Stop-ManagedService $config 'detached-wrapper' | Out-Null
    if (@(Get-PortOwner $detachedPort).Count -ne 0 -or (Test-Path -LiteralPath $detachedRecordPath)) { throw 'Verified detached listener stop left a listener or record.' }
    $script:detachedListenerPids = @($script:detachedListenerPids | Where-Object { $_ -ne [int]$detachedRecord.listener_pid })

    $mismatchPort = Get-AvailableLoopbackPort
    $mismatchProcess = Start-TestManagedService $config 'mismatch' $mismatchPort @{} $shellPath $temporaryRoot
    $mismatchRecordPath = Get-ServiceRecordPath $config 'mismatch'
    $originalRecordJson = Get-Content -LiteralPath $mismatchRecordPath -Raw -Encoding UTF8
    $mismatchMutations = @(
        @{ Label='PID'; Apply={ param($record) $record.pid = $PID } },
        @{ Label='start time'; Apply={ param($record) $record.startedUtc = '2000-01-01T00:00:00.0000000Z' } },
        @{ Label='executable path'; Apply={ param($record) $record.executablePath = $shellPath + '.mismatch' } },
        @{ Label='command feature'; Apply={ param($record) $record.commandFeature = 'not-the-listener-command' } }
    )
    foreach ($mutation in $mismatchMutations) {
        $record = $originalRecordJson | ConvertFrom-Json
        & $mutation.Apply $record
        $record | ConvertTo-Json | Set-Content -LiteralPath $mismatchRecordPath -Encoding UTF8
        $check = Test-RecordedProcess $config 'mismatch'
        if ($check.Valid) { throw "$($mutation.Label) mismatch was unexpectedly accepted." }
        Stop-ManagedService $config 'mismatch' | Out-Null
        if (-not (Get-Process -Id $mismatchProcess.Id -ErrorAction SilentlyContinue)) { throw "$($mutation.Label) mismatch stopped the process." }
    }
    Set-Content -LiteralPath $mismatchRecordPath -Value $originalRecordJson -Encoding UTF8
    Stop-ManagedService $config 'mismatch' | Out-Null
    if (Get-Process -Id $mismatchProcess.Id -ErrorAction SilentlyContinue) { throw 'Matching record did not allow a managed stop.' }
    $script:fakeProcesses = @($script:fakeProcesses | Where-Object { $_.Id -ne $mismatchProcess.Id })

    $unknownPort = Get-AvailableLoopbackPort
    $unknownCommand = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $unknownPort + '); $listener.Start(); Start-Sleep -Seconds 90'
    $unknownProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile', '-Command', $unknownCommand) -WindowStyle Hidden -PassThru
    $script:fakeProcesses += $unknownProcess
    Start-Sleep -Milliseconds 300
    Assert-Throws { Assert-PortAvailable $config 'unknown-service' $unknownPort } 'Unknown port owner protection'
    if (-not (Get-Process -Id $unknownProcess.Id -ErrorAction SilentlyContinue)) { throw 'Unknown port process was unexpectedly stopped.' }

    foreach ($definition in $serviceDefinitions) {
        $process = $started[$definition.ServiceName]
        Stop-ManagedService $config $definition.ServiceName | Out-Null
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { throw "$($definition.ServiceName) was not safely stopped." }
        Stop-ManagedService $config $definition.ServiceName | Out-Null
        $script:fakeProcesses = @($script:fakeProcesses | Where-Object { $_.Id -ne $process.Id })
    }

    Write-Host 'OPS-LAN-RECORD-FIX1 tests passed (stable names, records, environment restoration, status, safe stop, mismatches, unknown port, repeated stop).' -ForegroundColor Green
} finally {
    foreach ($process in $script:fakeProcesses) {
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    foreach ($listenerPid in $script:detachedListenerPids) {
        if (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue) { Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue }
    }
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) {
        # Windows can retain redirected log handles briefly after the verified
        # child process exits. Retry only inside this test's GUID temp folder.
        for ($attempt = 0; $attempt -lt 10 -and (Test-Path -LiteralPath $temporaryRoot); $attempt++) {
            try { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction Stop } catch { Start-Sleep -Milliseconds 300 }
        }
        if (Test-Path -LiteralPath $temporaryRoot) { Write-Warning "Test cleanup could not remove $temporaryRoot because Windows still holds a redirected-log handle." }
    }
}
