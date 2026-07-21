$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if ((Test-Http 'http://127.0.0.1:8000/api/health') -or (Test-PortListening 8000)) {
    throw 'The backend is running. Run scripts\stop.ps1 before rebuilding the index.'
}

$venvPython = Join-Path $script:BackendDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'The backend virtual environment is missing. Run scripts\start.ps1 first.'
}

Write-Host "Only this project vector store will be rebuilt: $(Join-Path $script:BackendDir 'vector_db')"
& $venvPython (Join-Path $script:BackendDir 'scripts\rebuild_index.py')
if ($LASTEXITCODE -ne 0) { throw 'Index rebuild failed.' }
