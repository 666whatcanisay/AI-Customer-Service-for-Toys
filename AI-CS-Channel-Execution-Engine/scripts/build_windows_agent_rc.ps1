[CmdletBinding()]
param(
    [string]$OutputRoot,
    [string]$PythonExecutable
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot 'dist\windows-rc'))
if (-not $OutputRoot) { $OutputRoot = $allowedOutputRoot }
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
if (-not $resolvedOutput.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must stay inside $allowedOutputRoot"
}
if (-not $PythonExecutable) {
    $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    $PythonExecutable = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
}

$compositionPath = Join-Path $repoRoot 'packaging\windows-agent\production-composition.json'
$composition = Get-Content -LiteralPath $compositionPath -Raw -Encoding UTF8 | ConvertFrom-Json
$releaseVersion = [string]$composition.release -replace '^AI-CS-Agent\s+', ''
if ($releaseVersion -notmatch '^\d+\.\d+\.\d+-rc\.\d+$') {
    throw "Unsupported release version: $releaseVersion"
}
$stageRoot = Join-Path $resolvedOutput '.stage'
$appStage = Join-Path $stageRoot 'app'
$packageRoot = Join-Path $resolvedOutput 'AI-CS-Agent'
if (Test-Path -LiteralPath $resolvedOutput) {
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}
foreach ($path in @(
    $appStage,
    (Join-Path $packageRoot 'exe'),
    (Join-Path $packageRoot 'config'),
    (Join-Path $packageRoot 'runtime\contracts'),
    (Join-Path $packageRoot 'logs'),
    (Join-Path $packageRoot 'scripts')
)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

$packageSource = Join-Path $appStage 'ai_cs_agent'
New-Item -ItemType Directory -Path $packageSource | Out-Null
foreach ($relative in $composition.source_allowlist) {
    $source = Join-Path $repoRoot ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Allowlisted source is missing: $relative"
    }
    Copy-Item -LiteralPath $source -Destination $packageSource
}

@(
    'from ai_cs_agent.cli import main'
    ''
    'raise SystemExit(main())'
) | Set-Content -LiteralPath (Join-Path $appStage '__main__.py') -Encoding UTF8

$forbiddenImports = @('channel_engine', 'pdd', 'sandbox', 'discovery', 'mock_server')
foreach ($sourceFile in Get-ChildItem -LiteralPath $packageSource -Filter '*.py') {
    $content = Get-Content -LiteralPath $sourceFile.FullName -Raw -Encoding UTF8
    foreach ($forbidden in $forbiddenImports) {
        if ($content -match "(?m)^\s*(from|import)\s+$([regex]::Escape($forbidden))(\.|\s|$)") {
            throw "Forbidden production import '$forbidden' in $($sourceFile.Name)"
        }
    }
}

$zipApp = Join-Path $packageRoot 'exe\ai-cs-agent.pyz'
& $PythonExecutable -m zipapp $appStage -o $zipApp
if ($LASTEXITCODE -ne 0) { throw 'zipapp build failed' }

$pythonBase = (& $PythonExecutable -c 'import sys; print(sys.base_prefix)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $pythonBase 'python312.dll'))) {
    throw 'A complete CPython 3.12 runtime is required to build the portable RC'
}
$pythonRuntime = Join-Path $packageRoot 'runtime\python'
New-Item -ItemType Directory -Path $pythonRuntime -Force | Out-Null
foreach ($name in @('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    $source = Join-Path $pythonBase $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $packageRoot 'exe')
    }
}
Copy-Item -LiteralPath (Join-Path $pythonBase 'Lib') -Destination $pythonRuntime -Recurse
Copy-Item -LiteralPath (Join-Path $pythonBase 'DLLs') -Destination $pythonRuntime -Recurse
$sitePackages = Join-Path $pythonRuntime 'Lib\site-packages'
if (Test-Path -LiteralPath $sitePackages) {
    $resolvedSitePackages = [System.IO.Path]::GetFullPath($sitePackages)
    if (-not $resolvedSitePackages.StartsWith($pythonRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to remove an unexpected site-packages path'
    }
    Remove-Item -LiteralPath $resolvedSitePackages -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $pythonBase 'LICENSE.txt') -Destination (Join-Path $pythonRuntime 'PYTHON-LICENSE.txt')
@(
    '..\runtime\python\Lib'
    '..\runtime\python\DLLs'
    '.'
    'import site'
) | Set-Content -LiteralPath (Join-Path $packageRoot 'exe\python312._pth') -Encoding ASCII

Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\windows-agent-rc\agent.example.json') -Destination (Join-Path $packageRoot 'config\agent.example.json')
$launcherPath = Join-Path $packageRoot 'scripts\start_ai_cs_agent.bat'
Copy-Item -LiteralPath (Join-Path $repoRoot 'scripts\windows\start_ai_cs_agent.bat') -Destination $launcherPath
$launcherContent = Get-Content -LiteralPath $launcherPath -Raw -Encoding UTF8
$launcherContent = $launcherContent -replace "`r?`n", "`r`n"
[System.IO.File]::WriteAllText(
    $launcherPath,
    $launcherContent,
    [System.Text.UTF8Encoding]::new($true)
)
Copy-Item -LiteralPath (Join-Path $repoRoot 'schemas\ai-cs-channel-engine-gateway-contract-v1.schema.json') -Destination (Join-Path $packageRoot 'runtime\contracts\ai-cs-channel-engine-gateway-contract-v1.schema.json')
Set-Content -LiteralPath (Join-Path $packageRoot 'runtime\.keep') -Value 'Runtime state is created here.' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $packageRoot 'logs\.keep') -Value 'Structured local logs are created here.' -Encoding UTF8

$files = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        size = $_.Length
    }
}
$manifest = [ordered]@{
    schema_version = '1.0'
    release = $composition.release
    protected_anchor = $composition.protected_anchor
    python_requirement = 'CPython 3.12 x64'
    bundled_python = $true
    gateway_contract_version = '1.0'
    exit_codes = [ordered]@{
        normal = 0
        configuration_error = 1
        gateway_unreachable = 2
        authentication_failed = 3
        runtime_error = 4
        browser_environment_error = 5
    }
    production_components = $composition.components
    excluded_components = $composition.excluded
    files = $files
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Encoding UTF8

$archive = Join-Path $resolvedOutput "AI-CS-Agent-$releaseVersion-windows-x64.zip"
Compress-Archive -LiteralPath $packageRoot -DestinationPath $archive -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force

Write-Output "package=$packageRoot"
Write-Output "archive=$archive"
Write-Output "archive_sha256=$((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant())"
