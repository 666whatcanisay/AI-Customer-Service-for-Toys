Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$helper = Join-Path $PSScriptRoot '..\Resolve-AiCsRepositoryRoot.ps1'
. $helper

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ai-cs-portable-layout-' + [Guid]::NewGuid().ToString('N'))
try {
    $monorepoRoot = Join-Path $temporaryRoot 'downloaded-project-any-name'
    $engineRoot = Join-Path $monorepoRoot 'AI-CS-Channel-Execution-Engine'
    foreach ($path in @(
        $engineRoot,
        (Join-Path $monorepoRoot 'backend'),
        (Join-Path $monorepoRoot 'platform_backend'),
        (Join-Path $monorepoRoot 'frontend'),
        (Join-Path $monorepoRoot 'contracts'),
        (Join-Path $monorepoRoot 'scripts\windows')
    )) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    Set-Content -LiteralPath (Join-Path $monorepoRoot 'scripts\windows\common_ai_customer_service.ps1') -Value '# sentinel' -Encoding UTF8

    $resolved = Resolve-AiCsRepositoryRoot $engineRoot
    if (-not [string]::Equals($resolved, [IO.Path]::GetFullPath($monorepoRoot), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Monorepo root was not resolved: $resolved"
    }

    $legacyParent = Join-Path $temporaryRoot 'legacy-layout'
    $legacyEngine = Join-Path $legacyParent 'AI-CS-Channel-Execution-Engine'
    $legacyAiCs = Join-Path $legacyParent 'AI-CS'
    foreach ($path in @(
        $legacyEngine,
        (Join-Path $legacyAiCs 'backend'),
        (Join-Path $legacyAiCs 'platform_backend'),
        (Join-Path $legacyAiCs 'frontend'),
        (Join-Path $legacyAiCs 'contracts'),
        (Join-Path $legacyAiCs 'scripts\windows')
    )) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    Set-Content -LiteralPath (Join-Path $legacyAiCs 'scripts\windows\common_ai_customer_service.ps1') -Value '# sentinel' -Encoding UTF8
    $legacyResolved = Resolve-AiCsRepositoryRoot $legacyEngine
    if (-not [string]::Equals($legacyResolved, [IO.Path]::GetFullPath($legacyAiCs), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Legacy sibling root was not resolved: $legacyResolved"
    }

    Write-Host 'Portable repository layout tests passed.' -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
