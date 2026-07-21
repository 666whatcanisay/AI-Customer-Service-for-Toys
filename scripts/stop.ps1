$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$stoppedFrontend = Stop-RecordedProcess 'frontend'
$stoppedBackend = Stop-RecordedProcess 'backend'

if ($stoppedFrontend) { Write-Host 'Frontend stop command completed.' }
if ($stoppedBackend) { Write-Host 'Backend stop command completed.' }
if (-not $stoppedFrontend -and -not $stoppedBackend) {
    Write-Host 'No processes recorded by this project were found.'
}
