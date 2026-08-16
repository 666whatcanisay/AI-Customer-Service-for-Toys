[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\AI-CS-Channel-Agent'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\dist\windows-client-v2\rc3'),
    [string]$PythonExecutable = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$BaselineRuntimePath
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$PythonExecutable = [System.IO.Path]::GetFullPath($PythonExecutable)
$BaselineRuntimePath = $(if ($BaselineRuntimePath) {
    [System.IO.Path]::GetFullPath($BaselineRuntimePath)
} else {
    Join-Path $InstallRoot 'app\channel-agent.pyz'
})
$version = '2.0.0rc3'
$baselineSha = 'a2f5f89f3656eeab2ad46deea39805de8d067e8978f5ee6f80e0f3839d75a31a'
$gatewayContractSha = 'e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $childPath = [System.IO.Path]::GetFullPath($Child)
    if (-not $childPath.StartsWith($parentPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside build root: $childPath"
    }
}

foreach ($required in @(
    $BaselineRuntimePath,
    (Join-Path $InstallRoot 'release-manifest.json'),
    $PythonExecutable,
    (Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentLauncher.cs')
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required RC3 input is missing: $required"
    }
}
if ((Get-Sha256 $BaselineRuntimePath) -ne $baselineSha) {
    throw 'Selected runtime is not the approved RC1 baseline.'
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stageParent = Join-Path $env:TEMP 'ChannelAgentRC3Build'
New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
$stageRoot = Join-Path $stageParent ([guid]::NewGuid().ToString('N'))
$packageRoot = Join-Path $stageRoot 'AI-CS-Channel-Agent'
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
Assert-ChildPath $stageParent $stageRoot

try {
    foreach ($item in Get-ChildItem -LiteralPath $InstallRoot -Force) {
        if ($item.Name -in @('.brand-upgrade-backups', '.rc3-upgrade-backups', 'brand-upgrade-manifest.json')) { continue }
        Copy-Item -LiteralPath $item.FullName -Destination $packageRoot -Recurse -Force
    }

    $runtimeEvidence = Join-Path $stageRoot 'runtime-minimal-diff.json'
    & $PythonExecutable (Join-Path $repoRoot 'scripts\build_channel_agent_rc3_runtime.py') `
        --baseline $BaselineRuntimePath `
        --repo-root $repoRoot `
        --output (Join-Path $packageRoot 'app\channel-agent.pyz') `
        --evidence $runtimeEvidence
    if ($LASTEXITCODE -ne 0) { throw 'RC3 runtime patch build failed.' }

    $launcherSource = Join-Path $repoRoot 'packaging\windows-client-v1\ChannelAgentLauncher.cs'
    $assemblyInfo = Join-Path $stageRoot 'ChannelAgentAssemblyInfo.cs'
    [System.IO.File]::WriteAllText(
        $assemblyInfo,
        @"
[assembly: System.Reflection.AssemblyTitle("AI-CS Channel Agent")]
[assembly: System.Reflection.AssemblyProduct("AI-CS Channel Agent")]
[assembly: System.Reflection.AssemblyCompany("AI-CS")]
[assembly: System.Reflection.AssemblyDescription("AI-CS Channel Agent desktop assistant")]
[assembly: System.Reflection.AssemblyVersion("2.0.0.3")]
[assembly: System.Reflection.AssemblyFileVersion("2.0.0.3")]
[assembly: System.Reflection.AssemblyInformationalVersion("2.0.0rc3")]
"@,
        [System.Text.UTF8Encoding]::new($true)
    )
    $compilerParameters = [System.CodeDom.Compiler.CompilerParameters]::new()
    $compilerParameters.GenerateExecutable = $true
    $compilerParameters.GenerateInMemory = $false
    $compilerParameters.OutputAssembly = Join-Path $packageRoot 'ChannelAgent.exe'
    $compilerParameters.CompilerOptions = '/target:winexe'
    $icon = Join-Path $packageRoot 'assets\branding\channel-agent.ico'
    if (Test-Path -LiteralPath $icon -PathType Leaf) {
        $compilerParameters.CompilerOptions += " /win32icon:`"$icon`""
    }
    foreach ($assembly in @('System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll')) {
        [void]$compilerParameters.ReferencedAssemblies.Add($assembly)
    }
    $provider = [Microsoft.CSharp.CSharpCodeProvider]::new()
    try {
        $result = $provider.CompileAssemblyFromFile(
            $compilerParameters,
            [string[]]@($launcherSource, $assemblyInfo)
        )
        $errors = @($result.Errors | Where-Object { -not $_.IsWarning })
        if ($errors.Count -gt 0) { throw "Launcher compilation failed:`n$($errors -join "`n")" }
    }
    finally {
        $provider.Dispose()
    }

    $packageInstallRoot = Join-Path $packageRoot 'install'
    foreach ($mapping in @(
        @('packaging\windows-client-v1\Install-AI-CS-Channel-Agent.ps1', 'Install-AI-CS-Channel-Agent.ps1'),
        @('packaging\windows-client-v1\Uninstall-AI-CS-Channel-Agent.ps1', 'Uninstall-AI-CS-Channel-Agent.ps1'),
        @('packaging\windows-client-v1\ChannelAgentShortcutName.ps1', 'ChannelAgentShortcutName.ps1'),
        @('scripts\upgrade_channel_agent_rc3.ps1', 'Upgrade-ChannelAgent-RC3.ps1')
    )) {
        Copy-Item -LiteralPath (Join-Path $repoRoot $mapping[0]) -Destination (Join-Path $packageInstallRoot $mapping[1]) -Force
    }
    foreach ($script in Get-ChildItem -LiteralPath $packageInstallRoot -Filter '*.ps1' -File) {
        $content = Get-Content -LiteralPath $script.FullName -Raw -Encoding UTF8
        [System.IO.File]::WriteAllText(
            $script.FullName,
            ($content -replace "`r?`n", "`r`n"),
            [System.Text.UTF8Encoding]::new($true)
        )
    }

    $oldManifest = Get-Content -LiteralPath (Join-Path $InstallRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtimeDiff = Get-Content -LiteralPath $runtimeEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest = [ordered]@{
        schema_version = '2.1'
        product = 'AI-CS Channel Agent Windows Client'
        version = $version
        client_resource_version = $version
        agent_runtime_version = $version
        brand_asset_version = '1.0'
        architecture = 'windows-x64'
        executable = 'ChannelAgent.exe'
        package_kind = 'installed-baseline-minimal-runtime-patch'
        config_contains_credentials = $false
        agent_control_protocol = '2.1'
        gateway_contract_sha256 = $gatewayContractSha
        runtime_baseline_sha256 = $baselineSha
        runtime_rc3_sha256 = [string]$runtimeDiff.rc3_sha256
        runtime_changed_members = @($runtimeDiff.changed_members)
        branding_status = $(if ($oldManifest.branding_status) { [string]$oldManifest.branding_status } else { 'official' })
        branding = $oldManifest.branding
        capabilities = @($oldManifest.capabilities)
        excluded = @($oldManifest.excluded)
        files = @()
    }
    $manifestPath = Join-Path $packageRoot 'release-manifest.json'
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    $manifest.files = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Where-Object {
        $_.FullName -ne $manifestPath
    } | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
            sha256 = Get-Sha256 $_.FullName
            size = $_.Length
        }
    })
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    $allowedDifferences = @(
        'ChannelAgent.exe',
        'app/channel-agent.pyz',
        'release-manifest.json',
        'install/Install-AI-CS-Channel-Agent.ps1',
        'install/Uninstall-AI-CS-Channel-Agent.ps1',
        'install/ChannelAgentShortcutName.ps1',
        'install/Upgrade-ChannelAgent-RC3.ps1'
    )
    $unexpected = [System.Collections.Generic.List[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $packageRoot -Recurse -File) {
        $relative = $file.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
        if ($relative -in $allowedDifferences) { continue }
        $installed = Join-Path $InstallRoot $relative.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $installed -PathType Leaf) -or (Get-Sha256 $installed) -ne (Get-Sha256 $file.FullName)) {
            [void]$unexpected.Add($relative)
        }
    }
    if ($unexpected.Count -gt 0) {
        throw "RC3 package includes unexpected differences: $($unexpected -join ', ')"
    }

    $windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $helperPath = Join-Path $packageInstallRoot 'ChannelAgentShortcutName.ps1'
    $shortcutName = & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -Command ". '$helperPath'; Get-ChannelAgentShortcutName"
    if ($LASTEXITCODE -ne 0 -or $shortcutName -ne ([string]::Concat('AI-CS ', [char]0x5BA2, [char]0x670D, [char]0x52A9, [char]0x624B, '.lnk'))) {
        throw 'Windows PowerShell 5.1 shortcut encoding gate failed.'
    }
    foreach ($script in Get-ChildItem -LiteralPath $packageInstallRoot -Filter '*.ps1' -File) {
        $bytes = [System.IO.File]::ReadAllBytes($script.FullName)
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        $containsNonAscii = $text.ToCharArray() | Where-Object { [int]$_ -gt 127 } | Select-Object -First 1
        $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
        if ($containsNonAscii -and -not $hasBom) { throw "PowerShell UTF-8 BOM gate failed: $($script.Name)" }
    }

    $archive = Join-Path $OutputDirectory "AI-CS-Channel-Agent-$version-windows-x64.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $archive -CompressionLevel Optimal
    Copy-Item -LiteralPath $runtimeEvidence -Destination (Join-Path $OutputDirectory 'runtime-minimal-diff.json') -Force
    Write-Output "package=$packageRoot"
    Write-Output "archive=$archive"
    Write-Output "archive_sha256=$(Get-Sha256 $archive)"
    Write-Output "runtime_sha256=$([string]$runtimeDiff.rc3_sha256)"
}
finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Assert-ChildPath $stageParent $stageRoot
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
