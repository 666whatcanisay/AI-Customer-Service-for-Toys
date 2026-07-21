$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')

Write-Host 'RAG AI Customer Service Status'
Write-Host '================'

try {
    $python = Resolve-PythonCommand
    Write-Host "Python: $(& $python --version 2>&1)"
} catch { Write-Host "Python: MISSING ($($_.Exception.Message))" -ForegroundColor Red }

try {
    $node = Resolve-NodeCommand
    Write-Host "Node.js: $(& $node --version 2>&1)"
} catch { Write-Host "Node.js: MISSING ($($_.Exception.Message))" -ForegroundColor Red }

$venvPython = Join-Path $script:BackendDir '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    Write-Host "Backend venv: $(& $venvPython --version 2>&1)"
} else {
    Write-Host 'Backend venv: MISSING' -ForegroundColor Yellow
}

Write-Host ''
Write-Host "Backend 8000: $(if (Test-PortListening 8000) { 'LISTEN' } else { 'DOWN' })"
Write-Host "Frontend 5173: $(if (Test-PortListening 5173) { 'LISTEN' } else { 'DOWN' })"

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3
    Write-Host "Health: $($health.data.status)"
} catch { Write-Host 'Health: DOWN' -ForegroundColor Red }

try {
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/status' -TimeoutSec 3
    Write-Host "RAG ready: $($status.ready)"
    Write-Host "LLM configured: $($status.model_configured)"
    Write-Host "Message: $($status.message)"
} catch { Write-Host 'RAG status: unavailable' -ForegroundColor Red }

try {
    $stats = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/knowledge/statistics' -TimeoutSec 3
    Write-Host "Documents: $($stats.data.document_count)"
    Write-Host "Chunks: $($stats.data.chunk_count)"
    Write-Host "Collection: $($stats.data.collection_name)"
} catch { Write-Host 'Knowledge statistics: unavailable' -ForegroundColor Yellow }

Write-Host ''
Write-Host "Logs: $script:LogDir"
