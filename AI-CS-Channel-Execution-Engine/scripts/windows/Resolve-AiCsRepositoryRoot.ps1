Set-StrictMode -Version Latest

function Test-AiCsRepositoryRoot([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $required = @(
        'backend',
        'platform_backend',
        'frontend',
        'contracts',
        'scripts\windows\common_ai_customer_service.ps1'
    )
    foreach ($relativePath in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $relativePath))) { return $false }
    }
    return $true
}

function Resolve-AiCsRepositoryRoot(
    [string]$EngineRoot,
    [string]$ExplicitRoot = ''
) {
    if ([string]::IsNullOrWhiteSpace($EngineRoot)) {
        throw 'CHANNEL_ENGINE_ROOT_REQUIRED'
    }

    if (-not [string]::IsNullOrWhiteSpace($ExplicitRoot)) {
        $candidate = [IO.Path]::GetFullPath($ExplicitRoot)
        if (-not (Test-AiCsRepositoryRoot $candidate)) {
            throw "AI_CS_REPOSITORY_ROOT_INVALID:$candidate"
        }
        return $candidate
    }

    $engine = [IO.Path]::GetFullPath($EngineRoot)
    $monorepoRoot = [IO.Path]::GetFullPath((Join-Path $engine '..'))
    if (Test-AiCsRepositoryRoot $monorepoRoot) { return $monorepoRoot }

    $legacySibling = [IO.Path]::GetFullPath((Join-Path $engine '..\AI-CS'))
    if (Test-AiCsRepositoryRoot $legacySibling) { return $legacySibling }

    throw "AI_CS_REPOSITORY_ROOT_NOT_FOUND:engine=$engine"
}
