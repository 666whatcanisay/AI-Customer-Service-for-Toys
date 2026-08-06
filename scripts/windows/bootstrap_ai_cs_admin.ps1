[CmdletBinding()]
param(
    [string]$ConfigPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[\p{L}\p{Nd}._-]{1,64}$')]
    [string]$Username,
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 80)]
    [string]$DisplayName
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

$resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
$config = Get-LocalConfig $resolvedConfigPath
Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
$platformEnvironment = Get-LocalPlatformEnvironment $config
$platformDirectory = Join-Path $config.RepositoryRoot 'platform_backend'

Write-Host 'Using the controlled Runtime configuration for the C database. Enter the temporary password only at the Python getpass prompt; first-login replacement is mandatory.' -ForegroundColor Cyan
Invoke-WithProcessEnvironment $platformEnvironment {
    Push-Location $platformDirectory
    try {
        & $config.PlatformPythonPath -m app.iam.cli --username $Username --display-name $DisplayName
        if ($LASTEXITCODE -ne 0) { throw "ADMIN bootstrap failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}
