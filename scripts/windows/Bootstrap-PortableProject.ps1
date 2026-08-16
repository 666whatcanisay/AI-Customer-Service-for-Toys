[CmdletBinding()]
param(
    [switch]$SkipPythonPackages,
    [switch]$SkipNodePackages,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtimeRoot = Join-Path $root '.runtime\portable'
$configDirectory = Join-Path $root '.runtime\phase-e\config'
$configPath = Join-Path $configDirectory 'green-standard.local.ps1'

function Resolve-Python312 {
    if (-not [string]::IsNullOrWhiteSpace($env:AI_CS_PYTHON312)) {
        $candidate = [IO.Path]::GetFullPath($env:AI_CS_PYTHON312)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw 'AI_CS_PYTHON312 does not point to a file.'
        }
        $version = (& $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($LASTEXITCODE -ne 0 -or $version -ne '3.12') {
            throw 'AI_CS_PYTHON312 must point to Python 3.12.'
        }
        return $candidate
    }
    try {
        $candidate = (& py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -eq 0 -and $candidate) { return $candidate }
    } catch { }
    $existing = Join-Path $root 'platform_backend\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $existing) {
        $version = (& $existing -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($version -eq '3.12') { return $existing }
    }
    throw 'Python 3.12 is required. Install it from python.org, then rerun this script.'
}

function Ensure-Venv([string]$Directory, [string]$BootstrapPython) {
    $python = Join-Path $Directory '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        & $BootstrapPython -m venv (Join-Path $Directory '.venv')
        if ($LASTEXITCODE -ne 0) { throw "Failed to create venv: $Directory" }
    }
    return $python
}

function New-SecretFile([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return }
    $bytes = [byte[]]::new(48)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    [IO.File]::WriteAllText($Path, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
}

$bootstrapPython = Resolve-Python312
$backendPython = Ensure-Venv (Join-Path $root 'backend') $bootstrapPython
$platformPython = Ensure-Venv (Join-Path $root 'platform_backend') $bootstrapPython
$engineRoot = Join-Path $root 'AI-CS-Channel-Execution-Engine'
$enginePython = Ensure-Venv $engineRoot $bootstrapPython

if (-not $SkipPythonPackages) {
    & $backendPython -m pip install --upgrade pip
    & $backendPython -m pip install -r (Join-Path $root 'backend\requirements.portable.txt')
    & $platformPython -m pip install --upgrade pip
    & $platformPython -m pip install -r (Join-Path $root 'platform_backend\requirements.portable.txt')
    & $enginePython -m pip install --upgrade pip
    & $enginePython -m pip install -e "$engineRoot[dev]"
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}

if (-not $SkipNodePackages) {
    Push-Location (Join-Path $root 'frontend')
    try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend npm ci failed.' } } finally { Pop-Location }
    Push-Location (Join-Path $root 'admin_web')
    try { & pnpm.cmd install --frozen-lockfile; if ($LASTEXITCODE -ne 0) { throw 'Admin pnpm install failed.' } } finally { Pop-Location }
}

if (-not $SkipBuild) {
    Push-Location (Join-Path $root 'frontend')
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        & npm.cmd run build:agent
        if ($LASTEXITCODE -ne 0) { throw 'Agent UI build failed.' }
    } finally { Pop-Location }
    Push-Location (Join-Path $root 'admin_web')
    try { & pnpm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Admin build failed.' } } finally { Pop-Location }
}

New-Item -ItemType Directory -Path $runtimeRoot, $configDirectory, (Join-Path $runtimeRoot 'secrets') -Force | Out-Null
New-SecretFile (Join-Path $runtimeRoot 'secrets\internal-service.secret')
New-SecretFile (Join-Path $runtimeRoot 'secrets\gateway-hmac.secret')

$configContent = @'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$runtime = Join-Path $root '.runtime\portable'
$database = Join-Path $runtime 'platform.sqlite3'
@{
    RuntimeMode = 'standard'
    RepositoryRoot = $root
    GatewayEnabled = $false
    GatewayClientId = 'channel-engine'
    GatewayKeyId = 'gateway-key-v1'
    GatewaySecretReference = 'secrets\gateway-hmac.secret'
    InternalServiceSecretReference = 'secrets\internal-service.secret'
    ChannelAgentIntegrationEnabled = $false
    ChannelAgentServerUrl = ''
    RagPythonPath = (Join-Path $root 'backend\.venv\Scripts\python.exe')
    PlatformPythonPath = (Join-Path $root 'platform_backend\.venv\Scripts\python.exe')
    PnpmCommand = 'pnpm.cmd'
    RagPort = 8420
    PlatformPort = 8421
    CustomerWebPort = 8422
    AdminWebPort = 8423
    BindAddress = '127.0.0.1'
    AdminWebBindAddress = '127.0.0.1'
    CustomerWebUrl = 'http://127.0.0.1:8422/'
    AdminWebUrl = 'http://127.0.0.1:8423/'
    AdminEnableLanMode = $false
    AdminOpenBrowser = $false
    RagHealthPath = '/api/health'
    PlatformHealthPath = '/health'
    OllamaModel = 'qwen3.5:9b'
    OllamaBaseUrl = 'http://127.0.0.1:11434'
    PlatformDatabaseUrl = 'sqlite:///' + ($database.Replace('\','/'))
    PlatformDatabaseBindingPath = "$database.binding.json"
    PlatformDatabaseEnvironmentId = 'AI_CS_PORTABLE_DEVELOPMENT'
    PlatformRequireDatabaseIdentity = $true
    RagKnowledgeBasePath = (Join-Path $root 'backend\knowledge_base')
    RagVectorDbPath = (Join-Path $root 'backend\vector_db')
    RagLogDirectory = (Join-Path $runtime 'logs')
    RagPrimaryCollectionName = 'documents'
    RagActiveCollectionName = 'portable_development'
    PlatformKnowledgeMaterialStorageDirectory = (Join-Path $runtime 'knowledge-materials')
    TestKnowledgePackageId = ''
    AutoSyncTestKnowledge = $false
    CorsAllowedOrigins = @('http://127.0.0.1:8422')
    OpenBrowser = $true
    RuntimeDirectory = $runtime
    TestDataPackagePath = ''
    AutoImportTestData = $false
    EnableLanMode = $false
    LanAddress = 'auto'
    PreferredInterfaceAlias = ''
    AllowPublicNetwork = $false
}
'@
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    [IO.File]::WriteAllText($configPath, $configContent, [Text.UTF8Encoding]::new($false))
}

$config = & $configPath
$bindingPath = [IO.Path]::GetFullPath([string]$config.PlatformDatabaseBindingPath)
$databasePath = $bindingPath -replace '\.binding\.json$', ''
if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
    $oldDatabaseUrl = $env:DATABASE_URL
    try {
        $env:DATABASE_URL = [string]$config.PlatformDatabaseUrl
        Push-Location (Join-Path $root 'platform_backend')
        & $platformPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Platform migration failed.' }
        $sourceCommit = (& git.exe -C $root rev-parse HEAD).Trim()
        & $platformPython -m app.runtime_database_identity bind-new `
            --database $databasePath --binding $bindingPath `
            --environment-id $config.PlatformDatabaseEnvironmentId `
            --source-commit $sourceCommit
        if ($LASTEXITCODE -ne 0) { throw 'Platform database identity binding failed.' }
    } finally {
        Pop-Location
        $env:DATABASE_URL = $oldDatabaseUrl
    }
}

& (Join-Path $PSScriptRoot 'Doctor-PortableProject.ps1') -RequireRuntime
if ($LASTEXITCODE -ne 0) { throw 'Portable project doctor failed.' }
Write-Host 'BOOTSTRAP_PORTABLE_PROJECT=PASS' -ForegroundColor Green
Write-Host 'Next: .\scripts\windows\Start-PortableProject.ps1'
