[CmdletBinding()]
param([switch]$RequireRuntime)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$failures = [Collections.Generic.List[string]]::new()

function Test-Command([string]$Name, [string[]]$Arguments) {
    try {
        $command = Get-Command $Name -ErrorAction Stop
        $allOutput = @(& $command.Source @Arguments 2>&1)
        $commandSucceeded = $?
        if (-not $commandSucceeded) { throw "$Name could not run" }
        $output = $allOutput | Select-Object -First 1
        Write-Host "[PASS] $Name $output" -ForegroundColor Green
    }
    catch {
        $script:failures.Add("Missing or unusable command: $Name")
        Write-Host "[FAIL] $Name - $($_.Exception.Message)" -ForegroundColor Red
    }
}

foreach ($relativePath in @(
    'backend', 'platform_backend', 'frontend', 'admin_web', 'contracts',
    'AI-CS-Channel-Execution-Engine', 'scripts\windows'
)) {
    if (Test-Path -LiteralPath (Join-Path $root $relativePath)) {
        Write-Host "[PASS] $relativePath"
    } else {
        $failures.Add("Missing repository entry: $relativePath")
        Write-Host "[FAIL] $relativePath" -ForegroundColor Red
    }
}

Test-Command 'git.exe' @('--version')
Test-Command 'node.exe' @('--version')
Test-Command 'npm.cmd' @('--version')
Test-Command 'pnpm.cmd' @('--version')
try {
    if (-not [string]::IsNullOrWhiteSpace($env:AI_CS_PYTHON312)) {
        $python = [IO.Path]::GetFullPath($env:AI_CS_PYTHON312)
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw 'AI_CS_PYTHON312 does not point to a file'
        }
        $version = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($LASTEXITCODE -ne 0 -or $version -ne '3.12') {
            throw 'AI_CS_PYTHON312 must point to Python 3.12'
        }
    } else {
        $python = & py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $python) { throw 'Python 3.12 missing' }
    }
    Write-Host "[PASS] Python 3.12 $python" -ForegroundColor Green
} catch {
    $existing = Join-Path $root 'platform_backend\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $existing) {
        $version = & $existing -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq '3.12') {
            Write-Host "[PASS] Python 3.12 $existing" -ForegroundColor Green
        } else {
            $failures.Add('Python 3.12 is required')
        }
    } else {
        $failures.Add('Python 3.12 is required')
        Write-Host '[FAIL] Python 3.12' -ForegroundColor Red
    }
}

try {
    $ollamaVersion = & ollama.exe --version 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw 'Ollama unavailable' }
    Write-Host "[PASS] $ollamaVersion" -ForegroundColor Green
} catch {
    Write-Host '[WARN] Ollama is not installed; AI generation cannot start.' -ForegroundColor Yellow
}

if ($RequireRuntime) {
    foreach ($relativePath in @(
        'backend\.venv\Scripts\python.exe',
        'platform_backend\.venv\Scripts\python.exe',
        'AI-CS-Channel-Execution-Engine\.venv\Scripts\python.exe',
        'frontend\dist\index.html',
        'admin_web\dist\index.html',
        '.runtime\phase-e\config\green-standard.local.ps1'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $relativePath))) {
            $failures.Add("Runtime dependency missing: $relativePath")
        }
    }
    $enginePython = Join-Path $root 'AI-CS-Channel-Execution-Engine\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $enginePython -PathType Leaf) {
        try {
            & $enginePython -c "import channel_agent, fastapi, httpx, pydantic, sqlalchemy, uvicorn" 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'AI-CE Python packages are incomplete' }
            Write-Host '[PASS] AI-CE Python runtime imports' -ForegroundColor Green
        } catch {
            $failures.Add('AI-CE Python packages are incomplete; run Bootstrap-PortableProject.ps1')
            Write-Host '[FAIL] AI-CE Python runtime imports' -ForegroundColor Red
        }
    }
    $configPath = Join-Path $root '.runtime\phase-e\config\green-standard.local.ps1'
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        try {
            $config = & $configPath
            $bindingPath = [IO.Path]::GetFullPath([string]$config.PlatformDatabaseBindingPath)
            $databasePath = $bindingPath -replace '\.binding\.json$', ''
            foreach ($path in @($databasePath, $bindingPath)) {
                if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                    $failures.Add("Runtime database identity file missing: $path")
                }
            }
        } catch {
            $failures.Add("Runtime configuration is invalid: $($_.Exception.Message)")
        }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Host "[BLOCKED] $_" -ForegroundColor Red }
    exit 1
}
Write-Host 'PORTABLE_PROJECT_DOCTOR=PASS' -ForegroundColor Green
