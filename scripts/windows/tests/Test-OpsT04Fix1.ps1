Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$testSandboxRoot = Join-Path ([IO.Path]::GetTempPath()) ("ops-t04-fix1-" + [Guid]::NewGuid().ToString('N'))
$testRoot = Join-Path $testSandboxRoot 'AI-CS'
$configPath = Join-Path $testRoot 'config.local.ps1'
$statusScript = Join-Path $PSScriptRoot '..\status_ai_customer_service.ps1'
$startScript = Join-Path $PSScriptRoot '..\start_ai_customer_service.ps1'
$commonScript = Join-Path $PSScriptRoot '..\common_ai_customer_service.ps1'
$shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$platformProbePath = (Get-Command where.exe -ErrorAction Stop).Source
$fakeProcess = $null

function Invoke-StatusFixture {
    param([Parameter(Mandatory = $true)][string]$Path)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell can surface a child process' stderr as a
        # NativeCommandError. The degraded-state fixtures intentionally emit
        # diagnostics, so capture them for assertions instead of terminating.
        $ErrorActionPreference = 'Continue'
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $statusScript -ConfigPath $Path 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{ Output = @($output); ExitCode = $exitCode }
}

try {
    New-Item -ItemType Directory -Force -Path @($testRoot, (Join-Path $testRoot 'backend'), (Join-Path $testRoot 'frontend'), (Join-Path $testRoot 'platform_backend')) | Out-Null
    @"
@{
    RepositoryRoot = '$($testRoot.Replace("'", "''"))'
    RagPythonPath = '$($shellPath.Replace("'", "''"))'
    # The status script invokes the platform Python for a migration probe.
    # Use a fast failing executable instead of an interactive PowerShell host.
    PlatformPythonPath = '$($platformProbePath.Replace("'", "''"))'
    PnpmCommand = '$($shellPath.Replace("'", "''"))'
    RagPort = 65401; CustomerWebPort = 65402; PlatformPort = 65403; BindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:65402/'
    RagHealthPath = '/api/health'; PlatformHealthPath = '/health'; OllamaModel = 'qwen3.5:9b'
    CorsAllowedOrigins = @('http://127.0.0.1:65402'); OpenBrowser = `$false
    RuntimeDirectory = '$((Join-Path $testRoot 'runtime').Replace("'", "''"))'
    TestDataPackagePath = ''; AutoImportTestData = `$false
}
"@ | Set-Content -LiteralPath $configPath -Encoding UTF8

    $syntaxFiles = Get-ChildItem (Join-Path $PSScriptRoot '..') -Filter '*.ps1' -File
    foreach ($file in $syntaxFiles) {
        $tokens=$null; $errors=$null
        [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "PowerShell 语法失败：$($file.Name)" }
    }
    $pidAssignments = rg -n --glob '*.ps1' '(?i)\$pid\s*=' (Join-Path $PSScriptRoot '..')
    if ($LASTEXITCODE -eq 0 -or $pidAssignments) { throw '仍存在 $pid 赋值，可能与内置 $PID 冲突。' }

    $statusResult = Invoke-StatusFixture $configPath
    $statusOutput = $statusResult.Output
    if ($statusResult.ExitCode -ne 0) { throw '全部服务未运行时状态脚本不应失败。' }
    foreach ($expected in @('C：未运行','A：未运行','B：未运行','未监听','health：不可用')) {
        if (($statusOutput -join "`n") -notmatch [regex]::Escape($expected)) { throw "缺少状态输出：$expected" }
    }

    . $commonScript
    $config = Get-LocalConfig $configPath
    $listenerCommand = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 65403); $listener.Start(); Start-Sleep -Seconds 90'
    $fakeProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',$listenerCommand) -WindowStyle Hidden -PassThru
    $listenerDeadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $listenerReady = @(Get-TcpListeningConnection 65403).Count -gt 0
        if (-not $listenerReady) { Start-Sleep -Milliseconds 100 }
    } until ($listenerReady -or [DateTime]::UtcNow -ge $listenerDeadline)
    if (-not $listenerReady) { throw 'C 测试监听器未在 5 秒内就绪。' }
    Save-ServiceRecord $config 'platform' $fakeProcess $shellPath $testRoot 'test C listener' 'TcpListener' 65403
    $onlyCResult = Invoke-StatusFixture $configPath
    $onlyCOutput = $onlyCResult.Output
    if ($onlyCResult.ExitCode -ne 0 -or ($onlyCOutput -join "`n") -notmatch 'C：运行中' -or ($onlyCOutput -join "`n") -notmatch '端口 65403：监听') {
        throw "只有 C 运行时未正确展示。实际输出：`n$($onlyCOutput -join "`n")"
    }
    if (Get-Process -Id $fakeProcess.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $fakeProcess.Id -Force }
    $fakeProcess = $null

    @{ name='platform'; pid=999999; executablePath=$shellPath; workingDirectory=$testRoot; startedUtc='2000-01-01T00:00:00.0000000Z'; commandFeature='never'; port=65403; repository_root=$testRoot; network_mode='LOCAL' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $config.RuntimeDirectory 'platform.json') -Encoding UTF8
    $staleResult = Invoke-StatusFixture $configPath
    $staleOutput = $staleResult.Output
    if ($staleResult.ExitCode -ne 0 -or ($staleOutput -join "`n") -notmatch 'C：未运行') {
        throw "过期 PID 未被安全地展示为未运行。exit=$($staleResult.ExitCode)；实际输出：`n$($staleOutput -join "`n")"
    }

    Remove-Item -LiteralPath $config.RuntimeDirectory -Recurse -Force
    $runtimeMissingResult = Invoke-StatusFixture $configPath
    $runtimeMissingOutput = $runtimeMissingResult.Output
    if ($runtimeMissingResult.ExitCode -ne 0 -or ($runtimeMissingOutput -join "`n") -notmatch 'C：未运行') { throw '缺少 .runtime 时状态脚本不应失败。' }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # The child launcher is expected to fail for this scenario.  Do not let
        # PowerShell 7 promote its non-zero exit code before the assertions run.
        $ErrorActionPreference = 'Continue'
        $startOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript -ConfigPath $configPath 2>&1
        $startExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $startOutputText = $startOutput -join "`n"
    # PowerShell may line-wrap a non-terminating error before the test captures it.
    # Collapse that presentation-only whitespace before checking the safety summary.
    $normalizedStartOutput = $startOutputText -replace '\s+', ' '
    if ($startExitCode -eq 0 -or $normalizedStartOutput -notmatch 'A \.venv' -or $normalizedStartOutput -notmatch 'C：未启动' -or $normalizedStartOutput -notmatch 'B：未启动') {
        throw "缺少 A .venv 时未给出完整安全提示。实际输出：`n$startOutputText"
    }
    Write-Host 'OPS-T04-FIX1 测试：PASS（状态未运行、仅 C、过期 PID、$PID 冲突、缺少 .runtime、缺少 A .venv 与语法）。' -ForegroundColor Green
} finally {
    if ($fakeProcess -and -not $fakeProcess.HasExited) { Stop-Process -Id $fakeProcess.Id -Force -ErrorAction SilentlyContinue }
    if ((Test-Path -LiteralPath $testSandboxRoot) -and
        (Split-Path -Parent $testSandboxRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) {
        Remove-Item -LiteralPath $testSandboxRoot -Recurse -Force
    }
}
