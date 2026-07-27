Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-runtime-version-' + [Guid]::NewGuid().ToString('N'))
$script:testProcess = $null

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try { & $Action } catch { return }
    throw "$Label should fail but did not."
}

try {
    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $identity = Get-RepositoryRuntimeIdentity $repositoryRoot
    if (-not $identity.Available -or $identity.GitSha -notmatch '^[0-9a-f]{40}$' -or [string]::IsNullOrWhiteSpace([string]$identity.SourceFingerprint)) {
        throw 'Repository identity could not be resolved for the test worktree.'
    }

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
    $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    $config = @{ RepositoryRoot=$repositoryRoot; RuntimeDirectory=(Join-Path $temporaryRoot 'runtime'); BindAddress='127.0.0.1'; LanMode=$false }
    $command = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $port + '); $listener.Start(); Start-Sleep -Seconds 60'
    $script:testProcess = Start-ManagedService $config 'runtime-version-test' $shellPath @('-NoProfile','-Command',$command) $temporaryRoot 'TcpListener' $port
    Start-Sleep -Milliseconds 300
    Update-ManagedServiceListenerRecord $config 'runtime-version-test' | Out-Null

    $recordPath = Get-ServiceRecordPath $config 'runtime-version-test'
    $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($field in @('repository_root','repository_git_sha','repository_source_state','repository_source_fingerprint','runtime_mode')) {
        if ($record.PSObject.Properties.Name -notcontains $field) { throw "Runtime record is missing $field." }
    }
    if ([string]$record.repository_git_sha -ne $identity.GitSha -or [string]$record.repository_source_fingerprint -ne $identity.SourceFingerprint -or [string]$record.runtime_mode -ne 'LOCAL') {
        throw 'Runtime record did not preserve the current repository identity.'
    }
    $matchingIdentity = Test-ManagedServiceRuntimeIdentity $config $record
    if (-not $matchingIdentity.Valid) { throw "Matching repository identity was rejected: $($matchingIdentity.Reason)" }
    Assert-ManagedRuntimeSourceConsistency $config @(@{Name='runtime-version-test';Port=$port})

    $tampered = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $tampered.repository_git_sha = ('0' * 40)
    $tampered | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    $tamperedIdentity = Test-ManagedServiceRuntimeIdentity $config $tampered
    if ($tamperedIdentity.Valid) { throw 'Tampered repository SHA was accepted.' }
    Assert-Throws { Assert-ManagedRuntimeSourceConsistency $config @(@{Name='runtime-version-test';Port=$port}) } 'Runtime source consistency guard'
    $processCheck = Test-RecordedProcess $config 'runtime-version-test'
    if (-not $processCheck.Valid) { throw 'Version mismatch changed the independent safe process identity decision.' }
    if (-not (Get-Process -Id $script:testProcess.Id -ErrorAction SilentlyContinue)) { throw 'Version mismatch unexpectedly stopped a process.' }

    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    Stop-ManagedService $config 'runtime-version-test' | Out-Null
    if (Get-Process -Id $script:testProcess.Id -ErrorAction SilentlyContinue) { throw 'Verified test service did not stop.' }
    $script:testProcess = $null
    Write-Host 'OPS runtime version identity tests passed.' -ForegroundColor Green
} finally {
    if ($script:testProcess -and (Get-Process -Id $script:testProcess.Id -ErrorAction SilentlyContinue)) { Stop-Process -Id $script:testProcess.Id -Force -ErrorAction SilentlyContinue }
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
