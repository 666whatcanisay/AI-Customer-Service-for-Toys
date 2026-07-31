Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-runtime-entry-alignment-' + [Guid]::NewGuid().ToString('N'))

function Assert-Throws([scriptblock]$Action, [string]$Label) {
    try { & $Action } catch { return }
    throw "$Label should fail but did not."
}

try {
    foreach ($path in @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\status_ai_customer_service.ps1',
        'scripts\windows\start_target_pilot.ps1'
    )) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $repositoryRoot $path), [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "$path has a PowerShell syntax error: $($errors[0].Message)" }
    }

    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null

    $scriptRoot = Join-Path $temporaryRoot 'repo\scripts\windows'
    $formalConfigDirectory = Join-Path $temporaryRoot 'repo\.runtime\phase-e\config'
    New-Item -ItemType Directory -Force -Path $scriptRoot, $formalConfigDirectory | Out-Null
    $legacyConfig = Join-Path $scriptRoot 'config.local.ps1'
    $formalConfig = Join-Path $formalConfigDirectory 'green-standard.local.ps1'
    Set-Content -LiteralPath $formalConfig -Value '@{}' -Encoding UTF8
    if ((Resolve-AiCustomerServiceConfigPath '' $scriptRoot) -ne $formalConfig) { throw 'Formal runtime config fallback was not selected.' }
    Set-Content -LiteralPath $legacyConfig -Value '@{}' -Encoding UTF8
    if ((Resolve-AiCustomerServiceConfigPath '' $scriptRoot) -ne $legacyConfig) { throw 'Legacy explicit local config must retain priority.' }
    if ((Resolve-AiCustomerServiceConfigPath 'X:\explicit\config.ps1' $scriptRoot) -ne 'X:\explicit\config.ps1') { throw 'Explicit ConfigPath was not preserved.' }

    $runtimeDirectory = Join-Path $temporaryRoot 'runtime'
    $managedRepository = Join-Path $temporaryRoot 'managed-repository'
    New-Item -ItemType Directory -Force -Path $runtimeDirectory, $managedRepository | Out-Null
    $config = @{ RepositoryRoot=$managedRepository; RuntimeDirectory=$runtimeDirectory; LanMode=$false }

    if ((Resolve-StandardRuntimeNetworkMode $config 'Auto') -ne 'LOCAL') { throw 'Auto without records must preserve configured LOCAL mode.' }
    if ((Resolve-StandardRuntimeNetworkMode $config 'Lan') -ne 'LAN') { throw 'Explicit LAN mode was not honored.' }
    Save-StandardRuntimeNetworkModePreference $config 'LAN'
    if ((Resolve-StandardRuntimeNetworkMode $config 'Auto') -ne 'LAN') { throw 'Auto did not preserve the durable LAN preference after records were absent.' }
    $preferencePath = Get-StandardRuntimeNetworkModePreferencePath $config
    $preference = Get-Content -LiteralPath $preferencePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($preference.schema -ne 'ai-cs-runtime-network-mode.v1' -or $preference.network_mode -ne 'LAN' -or $preference.repository_root -ne $managedRepository) { throw 'Runtime network preference receipt is incomplete.' }
    Remove-Item -LiteralPath $preferencePath -Force

    foreach ($name in @('platform','rag','customer-web','admin-web')) {
        @{ repository_root=$managedRepository; network_mode='LAN' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory "$name.json") -Encoding UTF8
    }
    if ((Get-RecordedRuntimeNetworkMode $config) -ne 'LAN') { throw 'Recorded LAN mode was not detected.' }
    if ((Resolve-StandardRuntimeNetworkMode $config 'Auto') -ne 'LAN') { throw 'Auto did not preserve recorded LAN mode.' }
    if ((Resolve-StandardRuntimeNetworkMode $config 'Local') -ne 'LOCAL') { throw 'Explicit LOCAL override was not honored.' }

    @{ repository_root=$managedRepository; network_mode='LOCAL' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'admin-web.json') -Encoding UTF8
    Assert-Throws { Resolve-StandardRuntimeNetworkMode $config 'Auto' | Out-Null } 'Mixed runtime record protection'

    @{ repository_root=(Join-Path $temporaryRoot 'other-repository'); network_mode='LAN' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'admin-web.json') -Encoding UTF8
    Assert-Throws { Resolve-StandardRuntimeNetworkMode $config 'Auto' | Out-Null } 'Foreign repository record protection'

    $startText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\start_ai_customer_service.ps1') -Raw -Encoding UTF8
    $statusText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\status_ai_customer_service.ps1') -Raw -Encoding UTF8
    $pilotText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\start_target_pilot.ps1') -Raw -Encoding UTF8
    if ($startText -notmatch 'Resolve-StandardRuntimeNetworkMode' -or $startText -notmatch 'start_lan_ai_customer_service\.ps1' -or $startText -notmatch 'Save-StandardRuntimeNetworkModePreference') { throw 'Generic start entry does not route and preserve the LAN mode.' }
    if ($statusText -notmatch 'Resolve-StandardRuntimeNetworkMode' -or $statusText -notmatch 'status_lan_ai_customer_service\.ps1') { throw 'Generic status entry does not route the recorded LAN mode.' }
    if ($pilotText -notmatch '-Mode \$Mode' -or $pilotText -notmatch '\$readinessMode') { throw 'Pilot entry does not forward and verify the selected network mode.' }

    $batchContents = @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'scripts\windows') -Filter '*.bat' -File | ForEach-Object {
        [pscustomobject]@{ Name=$_.Name; Content=(Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8) }
    })
    foreach ($entryScript in @('start_ai_customer_service.ps1','status_ai_customer_service.ps1','start_target_pilot.ps1')) {
        $matches = @($batchContents | Where-Object { $_.Content -match [regex]::Escape($entryScript) })
        if ($matches.Count -ne 1 -or $matches[0].Content -notmatch '-Mode Auto') { throw "Batch entry for $entryScript does not select Auto mode." }
    }

    Write-Host 'OPS runtime entry alignment tests passed.' -ForegroundColor Green
} finally {
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
