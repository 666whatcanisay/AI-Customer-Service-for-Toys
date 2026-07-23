Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-runtime-fix2-' + [Guid]::NewGuid().ToString('N'))

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try {
        & $Action
    } catch {
        return
    }
    throw "$Label should fail but did not."
}

try {
    foreach ($path in @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\status_ai_customer_service.ps1',
        'scripts\windows\stop_ai_customer_service.ps1',
        'scripts\windows\config.local.ps1.example'
    )) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $repositoryRoot $path),
            [ref]$tokens,
            [ref]$errors
        )
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
    $platformPython = Join-Path $temporaryRepository 'platform.exe'
    New-Item -ItemType File -Path $ragPython, $platformPython | Out-Null
    $legacyConfigPath = Join-Path $temporaryRoot 'legacy-config.ps1'
    @"
@{
    RepositoryRoot = '$temporaryRepository'
    RagPythonPath = '$ragPython'
    PlatformPythonPath = '$platformPython'
    PnpmCommand = '$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe'
    RagPort = 18000
    CustomerWebPort = 15173
    PlatformPort = 18011
    BindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:15173/'
    RagHealthPath = '/api/health'
    PlatformHealthPath = '/health'
    OllamaModel = 'qwen3.5:9b'
    CorsAllowedOrigins = @('http://127.0.0.1:15173')
    OpenBrowser = (1 -eq 0)
    RuntimeDirectory = '$temporaryRoot\runtime'
    TestDataPackagePath = ''
    AutoImportTestData = (1 -eq 0)
}
"@ | Set-Content -LiteralPath $legacyConfigPath -Encoding UTF8

    $config = Get-LocalConfig $legacyConfigPath
    if (
        $config.OllamaBaseUrl -ne 'http://127.0.0.1:11434' -or
        $config.PlatformDatabaseUrl -ne 'sqlite:///./platform.db' -or
        $config.TestKnowledgePackageId -ne 'PDD-SM-2026-001-TEST' -or
        -not $config.AutoSyncTestKnowledge
    ) {
        throw 'Legacy config did not receive the required optional defaults.'
    }

    Assert-Throws { Assert-OllamaReady @{ OllamaBaseUrl='http://127.0.0.1:1'; OllamaModel='qwen3.5:9b' } | Out-Null } 'Unavailable Ollama check'
    Assert-Throws { Assert-OllamaReady @{ OllamaBaseUrl='http://127.0.0.1:11434'; OllamaModel='does-not-exist:0' } | Out-Null } 'Missing Ollama model check'

    function Get-PortOwner([int]$Port) { @(99999) }
    Assert-Throws { Assert-PortAvailable $config 'rag' $config.RagPort } 'Unknown port owner protection'
    Remove-Item -LiteralPath Function:\Get-PortOwner -Force

    function Get-Json([string]$Url, [string]$Label) {
        [pscustomobject]@{ ready=$true; model_configured=$false; initialization_error=$null }
    }
    Assert-Throws { Assert-RagRuntimeReady $config | Out-Null } 'model_configured=false protection'
    Remove-Item -LiteralPath Function:\Get-Json -Force

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $nestedZip = Join-Path $temporaryRoot 'nested.zip'
    $archive = [IO.Compression.ZipFile]::Open($nestedZip, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($entryName in @('fixture/manifest.json', 'fixture/content.txt')) {
            $entry = $archive.CreateEntry($entryName)
            $writer = New-Object IO.StreamWriter($entry.Open())
            try { $writer.Write($entryName) } finally { $writer.Dispose() }
        }
    } finally {
        $archive.Dispose()
    }
    $normalizationConfig = @{ TestDataPackagePath=$nestedZip; RuntimeDirectory=(Join-Path $temporaryRoot 'runtime') }
    $normalizedZip = Get-NormalizedTestDataPackagePath $normalizationConfig
    $normalizedArchive = [IO.Compression.ZipFile]::OpenRead($normalizedZip)
    try {
        if (-not ($normalizedArchive.Entries | Where-Object { $_.FullName -eq 'manifest.json' })) {
            throw 'Nested ZIP was not normalized to a root manifest.'
        }
    } finally {
        $normalizedArchive.Dispose()
    }

    Write-Host 'OPS-RUNTIME-FIX2 unit checks passed.'
} finally {
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd('\')) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
