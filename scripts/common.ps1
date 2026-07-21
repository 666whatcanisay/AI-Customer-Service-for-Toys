$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:BackendDir = Join-Path $script:ProjectRoot 'backend'
$script:FrontendDir = Join-Path $script:ProjectRoot 'frontend'
$script:RuntimeDir = Join-Path $script:ProjectRoot '.runtime'
$script:LogDir = Join-Path $script:ProjectRoot 'logs'

function Resolve-PythonCommand {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Python 3.11 was not found. Install Python and make python.exe available.'
}

function Resolve-NodeCommand {
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        "$env:ProgramFiles\nodejs\node.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    $wingetNodes = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.*\node-*-win-x64\node.exe" -File -ErrorAction SilentlyContinue
    if ($wingetNodes) { return $wingetNodes[0].FullName }

    $codexRuntime = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $codexRuntime) { return $codexRuntime }
    throw 'Node.js 22 was not found. Install Node.js and make node.exe available.'
}

function Resolve-NpmCommand([string]$NodePath) {
    $npm = Join-Path (Split-Path -Parent $NodePath) 'npm.cmd'
    if (Test-Path -LiteralPath $npm) { return $npm }
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $programFilesNpm = "$env:ProgramFiles\nodejs\npm.cmd"
    if (Test-Path -LiteralPath $programFilesNpm) { return $programFilesNpm }
    $wingetNpm = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.*\node-*-win-x64\npm.cmd" -File -ErrorAction SilentlyContinue
    if ($wingetNpm) { return $wingetNpm[0].FullName }
    throw 'Node.js was found, but npm.cmd is missing. Repair the Node.js installation.'
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Test-PortListening([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Save-ProcessRecord([string]$Name, [System.Diagnostics.Process]$Process) {
    New-Item -ItemType Directory -Path $script:RuntimeDir -Force | Out-Null
    $record = [ordered]@{
        name = $Name
        pid = $Process.Id
        startedUtc = $Process.StartTime.ToUniversalTime().ToString('o')
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:RuntimeDir "$Name.json") -Encoding UTF8
}

function Stop-RecordedProcess([string]$Name) {
    $recordPath = Join-Path $script:RuntimeDir "$Name.json"
    if (-not (Test-Path -LiteralPath $recordPath)) {
        return $false
    }

    $removeRecord = $false
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        if ($process) {
            $actualStart = $process.StartTime.ToUniversalTime()
            $recordedStart = [datetime]::Parse($record.startedUtc).ToUniversalTime()
            if ([math]::Abs(($actualStart - $recordedStart).TotalSeconds) -lt 2) {
                & taskkill.exe /PID $process.Id /T /F | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to stop $Name process tree (PID $($process.Id))."
                }
                $removeRecord = $true
            } else {
                throw "Refusing to stop $Name because the recorded PID was reused."
            }
        } else {
            $removeRecord = $true
        }
    } finally {
        if ($removeRecord) {
            Remove-Item -LiteralPath $recordPath -Force -ErrorAction SilentlyContinue
        }
    }
    return $true
}
