[CmdletBinding()]
param(
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

$resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
$config = Get-LocalConfig $resolvedConfigPath
Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
$platformEnvironment = Get-LocalPlatformEnvironment $config
$platformDirectory = Join-Path $config.RepositoryRoot 'platform_backend'

Write-Host 'The three approved internal identities will be checked before creation.' -ForegroundColor Cyan
Write-Host 'Existing normalized usernames are skipped without password, role, or Store changes.' -ForegroundColor Cyan
Write-Host 'Enter the shared temporary password only at the Python getpass prompt; source, command line, logs, and Git never receive it.' -ForegroundColor Cyan

Invoke-WithProcessEnvironment $platformEnvironment {
    Push-Location $platformDirectory
    try {
        & $config.PlatformPythonPath -m app.iam.initial_users_cli
        if ($LASTEXITCODE -ne 0) { throw "Initial-user bootstrap failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}
