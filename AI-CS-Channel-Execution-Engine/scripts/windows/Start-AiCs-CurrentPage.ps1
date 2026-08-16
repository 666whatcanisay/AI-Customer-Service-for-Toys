[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$manager = Join-Path $repoRoot 'scripts\manage_current_page_auto_production.py'
$statusPath = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent\runtime\current-page-production-supervisor.json'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python runtime is missing: $python"
}

& $python $manager start | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Production supervisor failed to start.' }

$ready = $false
$status = $null
foreach ($attempt in 1..90) {
    Start-Sleep -Seconds 1
    try {
        $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $components = $status.components
        if (
            $status.supervisor_active -eq $true -and
            $status.automatic_navigation_enabled -eq $false -and
            $components.agent -eq $true -and
            $components.ai_gateway -eq $true -and
            $components.ai_platform -eq $true -and
            $components.host -eq $true
        ) {
            $ready = $true
            break
        }
    } catch {
        # Startup state is written atomically; retry while services come up.
    }
}

if (-not $ready) {
    throw 'Startup timed out. Open Run Details in the assistant.'
}

Write-Host ''
Write-Host 'AI-CS startup completed.' -ForegroundColor Green
if ($status.supervisor_state -eq 'READY') {
    Write-Host 'Current-conversation AUTO reply is running.' -ForegroundColor Green
} else {
    Write-Host 'Sign in to the dedicated PDD Edge and manually open one conversation.' -ForegroundColor Yellow
}
Write-Host 'Only the currently opened conversation is handled. Automatic navigation is disabled.'
