Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-admin-web-t05-' + [Guid]::NewGuid().ToString('N'))
$script:unknownProcesses = @()
$script:activeConfig = $null

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
    } catch {
        return
    }
    throw "$Label should fail but did not."
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

function Write-TestConfig([string]$Path, [string]$Repository, [string]$RagPython, [string]$PlatformPython, [int]$AdminPort) {
    $content = @"
@{
    RepositoryRoot = '$($Repository.Replace("'", "''"))'
    RagPythonPath = '$($RagPython.Replace("'", "''"))'
    PlatformPythonPath = '$($PlatformPython.Replace("'", "''"))'
    PnpmCommand = 'pnpm.cmd'
    RagPort = 18000; CustomerWebPort = 15173; PlatformPort = 18011; BindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:15173/'
    RagHealthPath = '/api/health'; PlatformHealthPath = '/health'
    OllamaModel = 'qwen3.5:9b'; CorsAllowedOrigins = @('http://127.0.0.1:15173'); OpenBrowser = `$false
    RuntimeDirectory = '$((Join-Path $temporaryRoot 'runtime').Replace("'", "''"))'; TestDataPackagePath = ''; AutoImportTestData = `$false
    InternalServiceSecretReference = '$((Join-Path $temporaryRoot 'runtime\secrets\internal-service.secret').Replace("'", "''"))'
    AdminWebPort = $AdminPort
    AdminWebBindAddress = '127.0.0.1'
    AdminWebUrl = 'http://127.0.0.1:$AdminPort/'
    AdminEnableLanMode = `$false
    AdminOpenBrowser = `$false
}
"@
    $content | Set-Content -LiteralPath $Path -Encoding UTF8
}

try {
    foreach ($path in @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\start_lan_ai_customer_service.ps1',
        'scripts\windows\status_ai_customer_service.ps1',
        'scripts\windows\status_lan_ai_customer_service.ps1',
        'scripts\windows\stop_ai_customer_service.ps1',
        'scripts\windows\open_admin_web.ps1',
        'scripts\windows\diagnose_lan_ai_customer_service.ps1'
    )) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $repositoryRoot $path), [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "$path has a PowerShell syntax error: $($errors[0].Message)" }
    }

    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $temporaryRepository = Join-Path $temporaryRoot 'repository'
    New-Item -ItemType Directory -Force -Path @(
        (Join-Path $temporaryRepository 'backend'),
        (Join-Path $temporaryRepository 'frontend'),
        (Join-Path $temporaryRepository 'platform_backend')
    ) | Out-Null
    $ragPython = Join-Path $temporaryRepository 'rag.exe'
    New-Item -ItemType File -Path $ragPython | Out-Null
    $platformPython = (Get-Command python.exe -ErrorAction Stop).Source
    $internalSecretPath = Join-Path $temporaryRoot 'runtime\secrets\internal-service.secret'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $internalSecretPath) | Out-Null
    [IO.File]::WriteAllText($internalSecretPath, ('i' * 32), [Text.UTF8Encoding]::new($false))
    $configPath = Join-Path $temporaryRoot 'config.local.ps1'
    $adminPort = Get-AvailableLoopbackPort
    Write-TestConfig $configPath $temporaryRepository $ragPython $platformPython $adminPort

    $config = Get-LocalConfig $configPath
    if ($config.AdminWebPort -ne $adminPort -or $config.AdminWebBindAddress -ne '127.0.0.1' -or $config.AdminEnableLanMode -or $config.AdminOpenBrowser) {
        throw 'Admin configuration was not parsed with the expected safe values.'
    }
    Assert-Throws { Assert-AdminWebDependencies $config | Out-Null } 'Missing admin_web preflight'

    $adminDirectory = Join-Path $temporaryRepository 'admin_web'
    $adminDist = Join-Path $adminDirectory 'dist'
    New-Item -ItemType Directory -Force -Path $adminDist | Out-Null
    Set-Content -LiteralPath (Join-Path $adminDist 'index.html') -Value '<html>admin production runtime test</html>' -Encoding UTF8
    & git -C $temporaryRepository init --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the isolated test repository.' }
    & git -C $temporaryRepository config user.email 'ops-test@example.invalid'
    & git -C $temporaryRepository config user.name 'OPS Test'
    & git -C $temporaryRepository add --all
    & git -C $temporaryRepository commit --quiet -m 'test fixture'
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit the isolated test repository fixture.' }
    Rename-Item -LiteralPath $adminDist -NewName 'dist.missing'
    Assert-Throws { Assert-AdminWebDependencies $config | Out-Null } 'Missing admin dist preflight'
    Rename-Item -LiteralPath (Join-Path $adminDirectory 'dist.missing') -NewName 'dist'
    Assert-AdminWebDependencies $config | Out-Null

    $unknownPort = Get-AvailableLoopbackPort
    $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $unknownProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',('$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $unknownPort + '); $listener.Start(); Start-Sleep -Seconds 90')) -WindowStyle Hidden -PassThru
    $script:unknownProcesses += $unknownProcess
    Start-Sleep -Milliseconds 300
    $config.AdminWebPort = $unknownPort
    $config.AdminWebUrl = "http://127.0.0.1:$unknownPort/"
    Assert-Throws { Start-AdminWebService $config | Out-Null } 'Unknown admin port owner protection'
    if (-not (Get-Process -Id $unknownProcess.Id -ErrorAction SilentlyContinue)) { throw 'Unknown port owner was stopped.' }
    $config.AdminWebPort = $adminPort
    $config.AdminWebUrl = "http://127.0.0.1:$adminPort/"

    $record = Start-AdminWebService $config
    $script:activeConfig = $config
    $recordPath = Get-ServiceRecordPath $config 'admin-web'
    $recordOnDisk = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($field in @('service_name','managed_pid','listener_pid','parent_pid','creation_time','executable_path','command_summary','working_directory','bind_address','port','url','started_at','repository_root','repository_git_sha','repository_source_state','repository_source_fingerprint','runtime_mode')) {
        if ($recordOnDisk.PSObject.Properties.Name -notcontains $field) { throw "Admin runtime record is missing $field." }
    }
    if ($recordOnDisk.service_name -ne 'admin-web' -or [int]$recordOnDisk.port -ne $adminPort -or $recordOnDisk.url -ne "http://127.0.0.1:$adminPort/") { throw 'Admin runtime record values are incorrect.' }
    if (-not (Test-Path -LiteralPath (Join-Path (Get-ServiceLogDirectory $config) 'admin-web.out.log')) -or -not (Test-Path -LiteralPath (Join-Path (Get-ServiceLogDirectory $config) 'admin-web.err.log'))) { throw 'Admin log files were not created.' }
    $status = Get-ServiceStatus $config 'admin-web' $adminPort $config.AdminWebUrl
    if (-not $status.Record.Valid) { throw "Admin status identity validation failed: $($status.State)." }
    if (-not (Test-ManagedServiceRunning $config 'admin-web' $adminPort)) {
        $runtimeIdentity = Test-ManagedServiceRuntimeIdentity $config $recordOnDisk
        $statusLines = @(& git -C $temporaryRepository status --porcelain=v1 --untracked-files=all 2>$null)
        throw "Admin repeat-start trust check did not accept the registered listener: $($runtimeIdentity.Reason); Git status: $($statusLines -join ', ')"
    }
    $statusScript = Join-Path $repositoryRoot 'scripts\windows\status_ai_customer_service.ps1'
    $statusOutput = & $statusScript -ConfigPath $configPath *>&1 | Out-String
    if ($statusOutput -notmatch 'Admin' -or $statusOutput -notmatch [regex]::Escape($config.AdminWebUrl)) { throw 'Status entry did not report the admin runtime.' }
    $openScript = Join-Path $repositoryRoot 'scripts\windows\open_admin_web.ps1'
    $openOutput = & $openScript -ConfigPath $configPath -NoLaunch *>&1 | Out-String
    if ($openOutput -notmatch [regex]::Escape($config.AdminWebUrl)) { throw 'Open-admin availability check did not report the local URL.' }
    Assert-Throws { Start-AdminWebService $config | Out-Null } 'Repeated admin startup protection'

    $originalRecord = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8
    $tamperedRecord = $originalRecord | ConvertFrom-Json
    $tamperedRecord.pid = $PID
    $tamperedRecord.managed_pid = $PID
    $tamperedRecord | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    $check = Test-RecordedProcess $config 'admin-web'
    if ($check.Valid) { throw 'Tampered admin PID was unexpectedly accepted.' }
    Stop-ManagedService $config 'admin-web' | Out-Null
    if (-not (Get-PortOwner $adminPort)) { throw 'Tampered record unexpectedly stopped the admin listener.' }
    Set-Content -LiteralPath $recordPath -Value $originalRecord -Encoding UTF8

    Stop-ManagedService $config 'admin-web' | Out-Null
    if (@(Get-PortOwner $adminPort).Count -ne 0) { throw 'Verified admin stop left a listener on the managed port.' }
    if (Test-Path -LiteralPath $recordPath) { throw 'Verified admin stop did not remove its runtime record.' }
    Stop-ManagedService $config 'admin-web' | Out-Null
    $script:activeConfig = $null

    foreach ($entry in @('start_ai_customer_service.ps1','stop_ai_customer_service.ps1','status_ai_customer_service.ps1','open_admin_web.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot "scripts\windows\$entry") -PathType Leaf)) { throw "Missing Windows entry: $entry" }
    }
    $adminBatchEntrypoints = @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'scripts\windows') -Filter '*.bat' | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw).Contains('open_admin_web.ps1') })
    if ($adminBatchEntrypoints.Count -ne 1) { throw 'The admin browser batch entry is missing or ambiguous.' }
    Write-Host 'OPS-T05 admin runtime tests passed (safe defaults, preflight, lifecycle, record, status, open check, unknown port, repeated start/stop, and tampered PID refusal).' -ForegroundColor Green
} finally {
    if ($script:activeConfig) {
        try { Stop-ManagedService $script:activeConfig 'admin-web' | Out-Null } catch { }
    }
    foreach ($process in $script:unknownProcesses) {
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) {
        for ($attempt = 0; $attempt -lt 10 -and (Test-Path -LiteralPath $temporaryRoot); $attempt++) {
            try { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction Stop } catch { Start-Sleep -Milliseconds 300 }
        }
        if (Test-Path -LiteralPath $temporaryRoot) { Write-Warning "Test cleanup could not remove $temporaryRoot because Windows still holds a redirected-log handle." }
    }
}
