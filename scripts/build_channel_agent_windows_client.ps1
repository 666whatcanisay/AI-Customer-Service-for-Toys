[CmdletBinding()]
param(
    [string]$OutputRoot,
    [string]$PythonExecutable,
    [string]$DesktopUiDist,
    [ValidateSet('official', 'fallback')]
    [string]$BrandingMode = 'official'
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot 'dist\windows-client-v2'))
if (-not $OutputRoot) { $OutputRoot = $allowedOutputRoot }
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
if (-not $resolvedOutput.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must stay inside $allowedOutputRoot"
}
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repoRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw 'A repository Python 3.12 virtual environment is required.'
}

$compositionPath = Join-Path $repoRoot 'packaging\windows-client-v2\production-composition.json'
$composition = Get-Content -LiteralPath $compositionPath -Raw -Encoding UTF8 | ConvertFrom-Json
$version = ([string]$composition.release -split ' ')[-1]
if ($version -notmatch '^\d+\.\d+\.\d+(?:rc\d+)?$') { throw "Unsupported version: $version" }
$engineCompatibility = '0.2.0rc3'
$gatewayContractSha = 'e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5'
& $PythonExecutable (Join-Path $repoRoot 'scripts\validate_channel_agent_composition.py') $repoRoot $compositionPath
if ($LASTEXITCODE -ne 0) { throw 'Production composition validation failed.' }
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
    (Join-Path $packageRoot 'assets\branding'),
    (Join-Path $packageRoot 'config'),
    (Join-Path $packageRoot 'install'),
    (Join-Path $packageRoot 'logs'),
    (Join-Path $packageRoot 'runtime\python')
)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }

$brandSpecPath = Join-Path $repoRoot 'packaging\windows-client-v2\branding\brand-assets.json'
$brandSpec = Get-Content -LiteralPath $brandSpecPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$brandSpec.product_version -ne $version) {
    throw "Brand asset version $($brandSpec.product_version) does not match package version $version."
}
$brandBuild = $null
$brandOutput = Join-Path $stageRoot 'branding'
$launcherIcon = $null
if ($BrandingMode -eq 'official') {
    # Brand Asset Gate is deliberately separate from composition, contract and
    # business validation. Official packages fail closed on altered assets;
    # emergency builds may explicitly select -BrandingMode fallback.
    & (Join-Path $repoRoot 'scripts\build_channel_agent_brand_assets.ps1') `
        -BrandManifestPath $brandSpecPath `
        -OutputDirectory $brandOutput
    $brandBuildPath = Join-Path $brandOutput 'brand-build-manifest.json'
    $brandBuild = Get-Content -LiteralPath $brandBuildPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($name in @(
        'channel-agent.ico',
        'channel-agent-avatar.png',
        'channel-agent-tray-normal.ico',
        'channel-agent-tray-warning.ico',
        'channel-agent-tray-error.ico',
        'channel-agent-tray-offline.ico',
        'brand-build-manifest.json'
    )) {
        $assetPath = Join-Path $brandOutput $name
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "Brand Asset Gate failed: missing generated asset $name"
        }
        Copy-Item -LiteralPath $assetPath -Destination (Join-Path $packageRoot 'assets\branding')
    }
    $launcherIcon = Join-Path $brandOutput 'channel-agent.ico'
}

foreach ($relative in $composition.source_allowlist) {
    $source = Join-Path $repoRoot ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing source: $relative" }
    $prefix = 'src/channel_agent/'
    if (-not $relative.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
        throw "Production source is outside channel_agent: $relative"
    }
    $withinPackage = $relative.Substring($prefix.Length).Replace('/', '\')
    $destination = Join-Path (Join-Path $appStage 'channel_agent') $withinPackage
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}
$packageFixtures = Join-Path $packageRoot 'config\fixtures'
New-Item -ItemType Directory -Path $packageFixtures -Force | Out-Null
foreach ($relative in $composition.offline_fixture_allowlist) {
    $source = Join-Path $repoRoot ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing fixture: $relative" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $packageFixtures (Split-Path $source -Leaf))
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
$sourceLib = Join-Path $pythonBase 'Lib'
$runtimeLib = Join-Path $runtime 'Lib'
New-Item -ItemType Directory -Path $runtimeLib -Force | Out-Null
Get-ChildItem -LiteralPath $sourceLib -Force | Where-Object { $_.Name -ne 'site-packages' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $runtimeLib -Recurse
}
Copy-Item -LiteralPath (Join-Path $pythonBase 'DLLs') -Destination $runtime -Recurse
$runtimeSite = Join-Path $runtime 'Lib\site-packages'
if (Test-Path -LiteralPath $runtimeSite) { Remove-Item -LiteralPath $runtimeSite -Recurse -Force }
New-Item -ItemType Directory -Path $runtimeSite -Force | Out-Null
foreach ($name in $composition.dependency_allowlist) {
    $source = Join-Path $venvSite $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing dependency: $name" }
    Copy-Item -LiteralPath $source -Destination $runtimeSite -Recurse
}
foreach ($pattern in @('annotated_types-*.dist-info','anyio-*.dist-info','certifi-*.dist-info','h11-*.dist-info','httpcore-*.dist-info','httpx-*.dist-info','idna-*.dist-info','pydantic-*.dist-info','pydantic_core-*.dist-info','typing_extensions-*.dist-info','typing_inspection-*.dist-info','websocket_client-*.dist-info')) {
    Get-ChildItem -LiteralPath $venvSite -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $runtimeSite -Recurse
    }
}

$launcherSource = Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentLauncher.cs'
$versionMatch = [regex]::Match($version, '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)(?:rc(?<rc>\d+))?$')
if (-not $versionMatch.Success) { throw "Cannot create Windows version resources for $version." }
$numericRevision = if ($versionMatch.Groups['rc'].Success) {
    [int]$versionMatch.Groups['rc'].Value
} else {
    0
}
$numericVersion = '{0}.{1}.{2}.{3}' -f `
    $versionMatch.Groups['major'].Value, `
    $versionMatch.Groups['minor'].Value, `
    $versionMatch.Groups['patch'].Value, `
    $numericRevision
$assemblyInfoPath = Join-Path $stageRoot 'ChannelAgentAssemblyInfo.cs'
@"
[assembly: System.Reflection.AssemblyTitle("AI-CS Channel Agent")]
[assembly: System.Reflection.AssemblyProduct("AI-CS Channel Agent")]
[assembly: System.Reflection.AssemblyCompany("AI-CS")]
[assembly: System.Reflection.AssemblyDescription("AI-CS Channel Agent desktop assistant")]
[assembly: System.Reflection.AssemblyVersion("$numericVersion")]
[assembly: System.Reflection.AssemblyFileVersion("$numericVersion")]
[assembly: System.Reflection.AssemblyInformationalVersion("$version")]
"@ | Set-Content -LiteralPath $assemblyInfoPath -Encoding UTF8

$compilerParameters = [System.CodeDom.Compiler.CompilerParameters]::new()
$compilerParameters.GenerateExecutable = $true
$compilerParameters.GenerateInMemory = $false
$compilerParameters.OutputAssembly = Join-Path $packageRoot 'ChannelAgent.exe'
$compilerParameters.CompilerOptions = '/target:winexe'
if ($launcherIcon) {
    $compilerParameters.CompilerOptions += " /win32icon:`"$launcherIcon`""
}
foreach ($assembly in @('System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll')) {
    [void]$compilerParameters.ReferencedAssemblies.Add($assembly)
}
$provider = [Microsoft.CSharp.CSharpCodeProvider]::new()
try {
    $launcherSources = [string[]]@($launcherSource, $assemblyInfoPath)
    $compileResult = $provider.CompileAssemblyFromFile(
        $compilerParameters,
        $launcherSources
    )
    $compileErrors = @($compileResult.Errors | Where-Object { -not $_.IsWarning })
    if ($compileErrors.Count -gt 0) {
        throw "Launcher compilation failed:`n$($compileErrors -join "`n")"
    }
}
finally {
    $provider.Dispose()
}

if (-not $DesktopUiDist) {
    $frontendRoot = Join-Path (Split-Path $repoRoot -Parent) 'AI-CS\frontend'
    $agentCandidate = Join-Path $frontendRoot 'dist-agent'
    $defaultCandidate = Join-Path $frontendRoot 'dist'
    if (Test-Path -LiteralPath $agentCandidate -PathType Container) {
        $DesktopUiDist = $agentCandidate
    } elseif (Test-Path -LiteralPath $defaultCandidate -PathType Container) {
        $DesktopUiDist = $defaultCandidate
    }
}
if ($DesktopUiDist) {
    $resolvedUi = [System.IO.Path]::GetFullPath($DesktopUiDist)
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedUi 'index.html') -PathType Leaf)) {
        throw 'Desktop UI dist must contain index.html.'
    }
    $packageUi = Join-Path $packageRoot 'ui'
    Copy-Item -LiteralPath $resolvedUi -Destination $packageUi -Recurse
    if ($BrandingMode -eq 'official') {
        Copy-Item -LiteralPath (Join-Path $brandOutput 'channel-agent-avatar.png') `
            -Destination (Join-Path $packageUi 'channel-agent-avatar.png')
        $indexPath = Join-Path $packageUi 'index.html'
        $indexContent = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8
        if ($indexContent -notmatch 'data-channel-agent-brand') {
            $favicon = '<link rel="icon" type="image/png" href="/channel-agent-avatar.png" data-channel-agent-brand="1.0" />'
            $indexContent = $indexContent -replace '</head>', "  $favicon`r`n  </head>"
            [System.IO.File]::WriteAllText(
                $indexPath,
                $indexContent,
                [System.Text.UTF8Encoding]::new($false)
            )
        }
    }
}
Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\channel-agent-foundation\agent.example.json') -Destination (Join-Path $packageRoot 'config\agent.example.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\channel-agent-foundation\agent.offline-replay.example.json') -Destination (Join-Path $packageRoot 'config\agent.offline-replay.example.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'deploy\channel-agent-foundation\upgrade-manifest.example.json') -Destination (Join-Path $packageRoot 'config\upgrade-manifest.example.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\Install-AI-CS-Channel-Agent.ps1') -Destination (Join-Path $packageRoot 'install')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\Uninstall-AI-CS-Channel-Agent.ps1') -Destination (Join-Path $packageRoot 'install')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentShortcutName.ps1') -Destination (Join-Path $packageRoot 'install')
Copy-Item -LiteralPath (Join-Path $repoRoot 'scripts\upgrade_channel_agent_brand_only.ps1') -Destination (Join-Path $packageRoot 'install\Upgrade-ChannelAgent-BrandOnly.ps1')
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\安装AI-CS客服端.bat') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $repoRoot 'packaging\windows-client-v1\客服电脑首次安装说明.txt') -Destination $packageRoot
foreach ($scriptName in @('Install-AI-CS-Channel-Agent.ps1', 'Uninstall-AI-CS-Channel-Agent.ps1', 'ChannelAgentShortcutName.ps1', 'Upgrade-ChannelAgent-BrandOnly.ps1')) {
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

$previousPythonHome = $env:PYTHONHOME
$previousPythonNoUserSite = $env:PYTHONNOUSERSITE
try {
    $env:PYTHONHOME = $runtime
    $env:PYTHONNOUSERSITE = '1'
    Push-Location $packageRoot
    try {
        & (Join-Path $runtime 'python.exe') (Join-Path $packageRoot 'app\channel-agent.pyz') version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Packaged Agent isolated startup validation failed.' }
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONHOME = $previousPythonHome
    $env:PYTHONNOUSERSITE = $previousPythonNoUserSite
}

$files = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        size = $_.Length
    }
}
[ordered]@{
    schema_version = '2.1'
    product = 'AI-CS Channel Agent Windows Client'
    version = $version
    client_resource_version = $version
    agent_runtime_version = $version
    channel_engine_compatibility = $engineCompatibility
    architecture = 'windows-x64'
    executable = 'ChannelAgent.exe'
    branding_status = $BrandingMode
    branding = [ordered]@{
        brand_version = [string]$brandSpec.brand_version
        product_version = [string]$brandSpec.product_version
        source_asset_sha256 = [string]$brandSpec.source_sha256
        icon_sizes = @($brandSpec.icon_sizes)
        executable_icon_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent.ico' } else { $null }
        )
        tray_normal_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent-tray-normal.ico' } else { $null }
        )
        tray_warning_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent-tray-warning.ico' } else { $null }
        )
        tray_error_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent-tray-error.ico' } else { $null }
        )
        tray_offline_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent-tray-offline.ico' } else { $null }
        )
        avatar_sha256 = $(
            if ($brandBuild) { [string]$brandBuild.outputs.'channel-agent-avatar.png' } else { $null }
        )
    }
    config_contains_credentials = $false
    agent_control_protocol = '2.1'
    gateway_contract_sha256 = $gatewayContractSha
    capabilities = @('first-launch-wizard','human-confirmed-lan-pairing','device-hmac-auth-v2.1','credential-manager-reference','tray-resident','versioned-brand-assets','desktop-assistant-ui','configuration-center','runtime-doctor','bounded-one-click-repair','atomic-config-rollback','browser-preserving-reload','start','stop','status','heartbeat','autostart','version','upgrade-check','enroll','binding-status','authorized-stores','single-active-store','engine-restart-recovery','encrypted-edge-spool','persist-before-ack','offline-replay-hard-lock','conversation-list-stage','message-capture-stage','host-ingest-stage','assistant-feed-stage','ai-suggestion-stage','signed-assistant-snapshot','offline-status','browser-open','browser-close','browser-status','isolated-browser-profile','pdd-login-open','pdd-login-status','pdd-login-observe-only')
    excluded = $composition.excluded
    files = $files
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $packageRoot 'release-manifest.json') -Encoding UTF8

& (Join-Path $repoRoot 'scripts\validate_channel_agent_brand_package.ps1') `
    -PackageRoot $packageRoot

Compress-Archive -LiteralPath $packageRoot -DestinationPath $archive -CompressionLevel Optimal
Remove-Item -LiteralPath $stageRoot -Recurse -Force
Write-Output "package=$packageRoot"
Write-Output "archive=$archive"
Write-Output "archive_sha256=$((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant())"
