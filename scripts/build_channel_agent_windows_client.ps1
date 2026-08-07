[CmdletBinding()]
param(
    [string]$OutputRoot,
    [string]$PythonExecutable
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot 'dist\windows-client-v1'))
if (-not $OutputRoot) { $OutputRoot = $allowedOutputRoot }
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
if (-not $resolvedOutput.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must stay inside $allowedOutputRoot"
}
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repoRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw 'A repository Python 3.12 virtual environment is required.'
}

$compositionPath = Join-Path $repoRoot 'packaging\windows-client-v1\production-composition.json'
$composition = Get-Content -LiteralPath $compositionPath -Raw -Encoding UTF8 | ConvertFrom-Json
$version = ([string]$composition.release -split ' ')[-1]
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "Unsupported version: $version" }
$stageRoot = Join-Path $resolvedOutput '.stage'
$appStage = Join-Path $stageRoot 'app'
$packageRoot = Join-Path $resolvedOutput 'AI-CS-Channel-Agent'
$archive = Join-Path $resolvedOutput "AI-CS-Channel-Agent-$version-windows-x64.zip"
if (Test-Path -LiteralPath $resolvedOutput) {
    if ($resolvedOutput -ne $allowedOutputRoot) { throw 'Refusing to clear unexpected output root.' }
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}
foreach ($path in @(
    (Join-Path $appStage 'channel_agent'),
    (Join-Path $packageRoot 'app'),
    (Join-Path $packageRoot 'config'),
    (Join-Path $packageRoot 'install'),
    (Join-Path $packageRoot 'logs'),
    (Join-Path $packageRoot 'runtime\python')
)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }

foreach ($relative in $composition.source_allowlist) {
    $source = Join-Path $repoRoot ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing source: $relative" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $appStage 'channel_agent')
}
@('from channel_agent.windows_app import main', '', 'raise SystemExit(main())') |
    Set-Content -LiteralPath (Join-Path $appStage '__main__.py') -Encoding UTF8
& $PythonExecutable -m zipapp $appStage -o (Join-Path $packageRoot 'app\channel-agent.pyz')
if ($LASTEXITCODE -ne 0) { throw 'zipapp build failed' }

$pythonBase = (& $PythonExecutable -c 'import sys; print(sys.base_prefix)').Trim()
$venvSite = (& $PythonExecutable -c "import site; print(next(path for path in site.getsitepackages() if path.lower().endswith('site-packages')))").Trim()
if (-not (Test-Path -LiteralPath (Join-Path $pythonBase 'python312.dll'))) {
    throw 'A complete CPython 3.12 x64 runtime is required.'
}
$runtime = Join-Path $packageRoot 'runtime\python'
foreach ($name in @('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    $source = Join-Path $pythonBase $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $runtime }
}
Copy-Item -LiteralPath (Join-Path $pythonBase 'Lib') -Destination $runtime -Recurse
Copy-Item -LiteralPath (Join-Path $pythonBase 'DLLs') -Destination $runtime -Recurse
$runtimeSite = Join-Path $runtime 'Lib\site-packages'
if (Test-Path -LiteralPath $runtimeSite) { Remove-Item -LiteralPath $runtimeSite -Recurse -Force }
New-Item -ItemType Directory -Path $runtimeSite -Force | Out-Null
foreach ($name in $composition.dependency_allowlist) {
    $source = Join-Path $venvSite $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing dependency: $name" }
    Copy-Item -LiteralPath $source -Destination $runtimeSite -Recurse
}
foreach ($pattern in @('annotated_types-*.dist-info','anyio-*.dist-info','certifi-*.dist-info','h11-*.dist-info','httpcore-*.dist-info','httpx-*.dist-info','idna-*.dist-info','pydantic-*.dist-info','pydantic_core-*.dist-info','typing_extensions-*.dist-info','typing_inspection-*.dist-info')) {
    Get-ChildItem -LiteralPath $venvSite -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $runtimeSite -Recurse
    }
}

$launcherSource = Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentLauncher.cs'
Add-Type -Path $launcherSource -OutputAssembly (Join-Path $packageRoot 'ChannelAgent.exe') -OutputType ConsoleApplication
Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\channel-agent-foundation\agent.example.json') -Destination (Join-Path $packageRoot 'config\agent.example.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\channel-agent-foundation\upgrade-manifest.example.json') -Destination (Join-Path $packageRoot 'config\upgrade-manifest.example.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\Install-AI-CS-Channel-Agent.ps1') -Destination (Join-Path $packageRoot 'install')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\Uninstall-AI-CS-Channel-Agent.ps1') -Destination (Join-Path $packageRoot 'install')
foreach ($scriptName in @('Install-AI-CS-Channel-Agent.ps1', 'Uninstall-AI-CS-Channel-Agent.ps1')) {
    $scriptPath = Join-Path $packageRoot "install\$scriptName"
    $scriptContent = Get-Content -LiteralPath $scriptPath -Raw -Encoding UTF8
    $scriptContent = $scriptContent -replace "`r?`n", "`r`n"
    [System.IO.File]::WriteAllText(
        $scriptPath,
        $scriptContent,
        [System.Text.UTF8Encoding]::new($true)
    )
}
Set-Content -LiteralPath (Join-Path $packageRoot 'logs\.keep') -Value 'Logs are written to the configured data directory.' -Encoding UTF8

$files = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        size = $_.Length
    }
}
[ordered]@{
    schema_version = '1.0'
    product = 'AI-CS Channel Agent Windows Client'
    version = $version
    architecture = 'windows-x64'
    executable = 'ChannelAgent.exe'
    config_contains_credentials = $false
    capabilities = @('start','stop','status','heartbeat','autostart','version','upgrade-check','enroll','binding-status','multi-store-sync','engine-restart-recovery','offline-status')
    excluded = $composition.excluded
    files = $files
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Encoding UTF8

Compress-Archive -LiteralPath $packageRoot -DestinationPath $archive -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force
Write-Output "package=$packageRoot"
Write-Output "archive=$archive"
Write-Output "archive_sha256=$((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant())"
