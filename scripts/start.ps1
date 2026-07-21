param(
    [switch]$NoBrowser,
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

New-Item -ItemType Directory -Force -Path $script:RuntimeDir, $script:LogDir | Out-Null

$python = Resolve-PythonCommand
$node = Resolve-NodeCommand
$npm = Resolve-NpmCommand $node
$venvDir = Join-Path $script:BackendDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirements = Join-Path $script:BackendDir 'requirements.txt'
$requirementsStamp = Join-Path $venvDir '.requirements.sha256'
$frontendStamp = Join-Path $script:FrontendDir 'node_modules\.package.sha256'

Write-Host "Python: $python"
Write-Host "Node.js: $node"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating the backend virtual environment...'
    & $python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python virtual environment.' }
}

if (-not (Test-Path -LiteralPath (Join-Path $script:BackendDir '.env'))) {
    Copy-Item -LiteralPath (Join-Path $script:BackendDir '.env.example') -Destination (Join-Path $script:BackendDir '.env')
}
if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendDir '.env'))) {
    Copy-Item -LiteralPath (Join-Path $script:FrontendDir '.env.example') -Destination (Join-Path $script:FrontendDir '.env')
}

if (-not $SkipInstall) {
    $requirementsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $requirements).Hash
    $installedHash = if (Test-Path -LiteralPath $requirementsStamp) { (Get-Content -LiteralPath $requirementsStamp -Raw).Trim() } else { '' }
    if ($requirementsHash -ne $installedHash) {
        Write-Host 'Installing or updating backend dependencies...'
        & $venvPython -m pip install --disable-pip-version-check -r $requirements
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
        Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -Encoding ASCII
    }

    $packageJson = Join-Path $script:FrontendDir 'package.json'
    $packageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packageJson).Hash
    $installedPackageHash = if (Test-Path -LiteralPath $frontendStamp) { (Get-Content -LiteralPath $frontendStamp -Raw).Trim() } else { '' }
    if ($packageHash -ne $installedPackageHash -or -not (Test-Path -LiteralPath (Join-Path $script:FrontendDir 'node_modules\vite\bin\vite.js'))) {
        Write-Host 'Installing or updating frontend dependencies...'
        Push-Location $script:FrontendDir
        try {
            & $npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        } finally {
            Pop-Location
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $frontendStamp) -Force | Out-Null
        Set-Content -LiteralPath $frontendStamp -Value $packageHash -Encoding ASCII
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) { throw 'The backend virtual environment is missing.' }
$vite = Join-Path $script:FrontendDir 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies are missing. Retry without -SkipInstall.' }

$startedBackend = $false
$startedFrontend = $false
try {
    if (Test-PortListening 8000) {
        if (-not (Test-Http 'http://127.0.0.1:8000/api/health')) {
            throw 'Port 8000 is occupied by another program.'
        }
        Write-Host 'The backend is already running.'
    } else {
        $backendProcess = Start-Process -FilePath $venvPython `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
            -WorkingDirectory $script:BackendDir `
            -RedirectStandardOutput (Join-Path $script:LogDir 'backend.out.log') `
            -RedirectStandardError (Join-Path $script:LogDir 'backend.err.log') `
            -WindowStyle Hidden -PassThru
        Save-ProcessRecord 'backend' $backendProcess
        $startedBackend = $true
    }

    Write-Host 'Waiting for the backend and local embedding model...'
    $backendReady = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/status' -TimeoutSec 3
            if ($status.initialization_error) { throw "RAG initialization failed: $($status.message)" }
            if ($status.ready) {
                $backendReady = $true
                break
            }
        } catch {
            if ($_.Exception.Message -like 'RAG initialization failed:*') { throw }
        }
        Start-Sleep -Seconds 1
    }
    if (-not $backendReady) { throw 'The backend did not initialize in 120 seconds. Check logs\backend.err.log.' }

    if (Test-PortListening 5173) {
        if (-not (Test-Http 'http://127.0.0.1:5173/')) {
            throw 'Port 5173 is occupied by another program.'
        }
        Write-Host 'The frontend is already running.'
    } else {
        $frontendProcess = Start-Process -FilePath $node `
            -ArgumentList @($vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort') `
            -WorkingDirectory $script:FrontendDir `
            -RedirectStandardOutput (Join-Path $script:LogDir 'frontend.out.log') `
            -RedirectStandardError (Join-Path $script:LogDir 'frontend.err.log') `
            -WindowStyle Hidden -PassThru
        Save-ProcessRecord 'frontend' $frontendProcess
        $startedFrontend = $true
    }

    $frontendReady = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-Http 'http://127.0.0.1:5173/') {
            $frontendReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $frontendReady) { throw 'The frontend failed to start. Check logs\frontend.err.log.' }

    Write-Host ''
    Write-Host 'RAG AI customer service started:' -ForegroundColor Green
    Write-Host 'Frontend: http://127.0.0.1:5173'
    Write-Host 'Backend:  http://127.0.0.1:8000'
    Write-Host 'API docs: http://127.0.0.1:8000/docs'
    if (-not $NoBrowser) {
        Start-Process 'http://127.0.0.1:5173'
    }
} catch {
    if ($startedFrontend) { Stop-RecordedProcess 'frontend' | Out-Null }
    if ($startedBackend) { Stop-RecordedProcess 'backend' | Out-Null }
    throw
}
