$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $scriptRoot 'bootstrap_ai_cs_initial_users.ps1'
$adminWrapper = Join-Path $scriptRoot 'bootstrap_ai_cs_admin.ps1'
$pythonCli = Join-Path (Split-Path -Parent $scriptRoot) '..\platform_backend\app\iam\initial_users_cli.py'

foreach ($path in @($wrapper, $adminWrapper, $pythonCli)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing bootstrap policy asset: $path" }
}

$wrapperText = Get-Content -LiteralPath $wrapper -Raw -Encoding UTF8
$adminText = Get-Content -LiteralPath $adminWrapper -Raw -Encoding UTF8
$cliText = Get-Content -LiteralPath $pythonCli -Raw -Encoding UTF8

if ($wrapperText -notmatch 'app\.iam\.initial_users_cli') { throw 'Initial-user wrapper does not invoke the controlled Python CLI.' }
if ($wrapperText -match '(?i)-password\b|password\s*=') { throw 'Initial-user wrapper must not accept or assign a password argument.' }
if ($cliText -notmatch 'getpass\.getpass') { throw 'Initial-user CLI must read the temporary credential through getpass.' }
if ($cliText -match 'password\s*=\s*["''][^"'']+["'']') { throw 'Initial-user CLI contains a hard-coded password literal.' }
if ($cliText -notmatch 'SKIPPED existing') { throw 'Initial-user CLI must report duplicate skips without overwrite.' }
if ($adminText -notmatch '\\p\{L\}') { throw 'ADMIN bootstrap username validation must support Unicode letters.' }

Write-Host 'PASS: initial-user bootstrap policy uses controlled config, getpass, Unicode usernames, and duplicate skip.' -ForegroundColor Green
