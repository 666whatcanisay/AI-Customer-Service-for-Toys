$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$scripts = @(
    (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1'),
    (Join-Path $repositoryRoot 'scripts\windows\start_ai_customer_service.ps1'),
    (Join-Path $repositoryRoot 'scripts\windows\start_lan_ai_customer_service.ps1')
)
foreach ($script in $scripts) {
    $parseErrors = $null
    [Management.Automation.Language.Parser]::ParseFile($script, [ref]$null, [ref]$parseErrors) | Out-Null
    if ($parseErrors) { throw "$script PowerShell parse failed: $($parseErrors.Message -join '; ')" }
}

$localLauncher = Get-Content -LiteralPath $scripts[1] -Raw -Encoding UTF8
$lanLauncher = Get-Content -LiteralPath $scripts[2] -Raw -Encoding UTF8
foreach ($source in @($localLauncher, $lanLauncher)) {
    if ($source -match 'vite\\bin\\vite\.js' -or $source -match "@\('dev'") {
        throw 'Production launcher must not invoke the Vite development server.'
    }
    if ($source -notmatch 'Start-CustomerWebService') {
        throw 'Production launcher must use the static production Web service.'
    }
}

$common = Get-Content -LiteralPath $scripts[0] -Raw -Encoding UTF8
foreach ($required in @(
    'INTERNAL_SERVICE_SECRET_FILE',
    'Get-AiCsInternalServiceHeaders',
    'serve_ai_cs_web.py',
    '--tls-cert',
    'CustomerWebTlsCertificateReference',
    'dist/index.html'
)) {
    if ($common -notmatch [regex]::Escape($required)) { throw "Runtime hardening marker missing: $required" }
}
Write-Host 'Production hardening runtime source checks PASS.' -ForegroundColor Green
