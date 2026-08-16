[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$statePath = Join-Path $repoRoot '.runtime\channel-agent-lan-host\host-state.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { Write-Host '状态：未启动'; exit 4 }
$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$engine = Get-Process -Id ([int]$state.engine_pid) -ErrorAction SilentlyContinue
$discovery = Get-Process -Id ([int]$state.discovery_pid) -ErrorAction SilentlyContinue
$operations = if ($state.operations_pid) { Get-Process -Id ([int]$state.operations_pid) -ErrorAction SilentlyContinue } else { $null }
$health = $false
$operationsHealth = $false
if (Test-Path -LiteralPath $python -PathType Leaf) {
    & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],verify=False,timeout=3,trust_env=False); raise SystemExit(0 if r.status_code==200 else 1)" "$($state.public_url)/health" 2>$null
    $health = $LASTEXITCODE -eq 0
    if ($state.operations_url) {
        $operationsHealthUrl = ([string]$state.operations_url -replace '/ops/console#devices$','') + '/health'
        & $python -c "import httpx,sys; r=httpx.get(sys.argv[1],timeout=3,trust_env=False); raise SystemExit(0 if r.status_code==200 else 1)" $operationsHealthUrl 2>$null
        $operationsHealth = $LASTEXITCODE -eq 0
    }
}
Write-Host "主机：$($state.host_id)"
Write-Host "地址：$($state.public_url)"
Write-Host "Channel Engine：$(if ($engine -and $health) {'READY'} else {'DEGRADED'})"
Write-Host "设备发现：$(if ($discovery) {'RUNNING'} else {'STOPPED'})"
Write-Host "运营控制台：$(if ($operations -and $operationsHealth) {'READY（设备状态来自18443）'} else {'DEGRADED'})"
if (-not $engine -or -not $discovery -or -not $operations -or -not $health -or -not $operationsHealth) { exit 4 }
exit 0
