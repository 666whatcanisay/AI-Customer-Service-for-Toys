Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-status-performance-' + [Guid]::NewGuid().ToString('N'))

try {
    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $managedRepository = Join-Path $temporaryRoot 'repository'
    $runtimeDirectory = Join-Path $temporaryRoot 'runtime'
    New-Item -ItemType Directory -Force -Path $managedRepository, $runtimeDirectory | Out-Null
    $config = @{
        RepositoryRoot = $managedRepository
        RuntimeDirectory = $runtimeDirectory
        CustomerWebPort = 5173
        LanAddress = 'auto'
        PreferredInterfaceAlias = ''
    }
    @{
        repository_root = $managedRepository
        network_mode = 'LAN'
        healthUrl = 'http://192.168.50.25:5173/'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'customer-web.json') -Encoding UTF8

    function Get-LanIpv4Candidates { throw 'Dynamic network discovery must not run for a valid managed record.' }
    $resolved = Resolve-LanStatusRuntimeConfig $config
    if ($resolved.LanStatusResolutionSource -ne 'MANAGED_RECORD' -or $resolved.CustomerWebBindAddress -ne '192.168.50.25') {
        throw 'Managed LAN runtime record was not selected for status.'
    }
    Remove-Item -LiteralPath Function:\Get-LanIpv4Candidates -Force

    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $probes = Get-ParallelHttpHealth @(
        @{ Name='one'; Url='http://127.0.0.1:59991/' },
        @{ Name='two'; Url='http://127.0.0.1:59992/' }
    ) 250
    $stopwatch.Stop()
    if ($probes.Count -ne 2 -or $probes['one'].Ok -or $probes['two'].Ok) {
        throw 'Parallel HTTP health failures were not represented explicitly.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$probes['one'].Error) -or [string]::IsNullOrWhiteSpace([string]$probes['two'].Error)) {
        throw 'Health failure reason is missing.'
    }
    if ($stopwatch.ElapsedMilliseconds -gt 2000) {
        throw "Parallel health checks exceeded the bounded test budget: $($stopwatch.ElapsedMilliseconds)ms"
    }

    $metadataStopwatch = [Diagnostics.Stopwatch]::StartNew()
    $currentMetadata = Get-ProcessMetadata $PID 1500
    $metadataStopwatch.Stop()
    if (-not $currentMetadata -or [int]$currentMetadata.ProcessId -ne $PID) {
        throw 'Bounded process metadata lookup did not return the current process.'
    }
    if ($metadataStopwatch.ElapsedMilliseconds -gt 3000) {
        throw "Process metadata lookup exceeded the bounded test budget: $($metadataStopwatch.ElapsedMilliseconds)ms"
    }
    $commonText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1') -Raw -Encoding UTF8
    if ($commonText -match 'Get-CimInstance\s+Win32_Process') {
        throw 'Unbounded Win32_Process enumeration remains in the runtime helper.'
    }

    $lanStatusText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\status_lan_ai_customer_service.ps1') -Raw -Encoding UTF8
    if ($lanStatusText -notmatch 'Resolve-LanStatusRuntimeConfig' -or $lanStatusText -notmatch 'Get-ParallelHttpHealth') {
        throw 'LAN status entry does not use record-first resolution and parallel health checks.'
    }
    Write-Host 'OPS status performance tests passed.' -ForegroundColor Green
} finally {
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd('\')) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
