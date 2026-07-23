Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:OpsScriptRoot = Split-Path -Parent $PSCommandPath
$script:OpsRepositoryRoot = [IO.Path]::GetFullPath((Join-Path $script:OpsScriptRoot '..\..'))
$script:OpsRuntimeRoot = if ($env:OPS_RUNTIME_ROOT) {
    [IO.Path]::GetFullPath($env:OPS_RUNTIME_ROOT)
} else {
    Join-Path $script:OpsRepositoryRoot '.runtime\windows'
}
$script:OpsStateRoot = Join-Path $script:OpsRuntimeRoot 'state'
$script:OpsLogRoot = Join-Path $script:OpsRuntimeRoot 'logs'
$script:OpsDataRoot = Join-Path $script:OpsRuntimeRoot 'data'
$script:OpsConfigPath = Join-Path $script:OpsRuntimeRoot 'config.psd1'
$script:OpsConfigExamplePath = Join-Path $script:OpsScriptRoot 'config.example.psd1'
$script:OpsAuditPath = Join-Path $script:OpsRuntimeRoot 'audit.jsonl'
$script:OpsPorts = [ordered]@{
    rag = 8000
    customer = 5173
    platform = 8011
    ollama = 11434
}

function Initialize-OpsRuntime {
    foreach ($path in @($script:OpsRuntimeRoot, $script:OpsStateRoot, $script:OpsLogRoot, $script:OpsDataRoot)) {
        [void](New-Item -ItemType Directory -Path $path -Force)
    }
    if (-not (Test-Path -LiteralPath $script:OpsConfigPath -PathType Leaf)) {
        Copy-Item -LiteralPath $script:OpsConfigExamplePath -Destination $script:OpsConfigPath
        Write-Host "已生成本机配置：$script:OpsConfigPath" -ForegroundColor Yellow
        Write-Host '如需指定 Python、Node 或 Ollama 路径，请编辑该文件后重新运行。' -ForegroundColor Yellow
    }
}

function Get-OpsConfig {
    Initialize-OpsRuntime
    $config = Import-PowerShellDataFile -LiteralPath $script:OpsConfigPath
    foreach ($required in @('RagPython', 'PlatformPython', 'NodeExecutable', 'OllamaExecutable', 'AutoStartOllama', 'OpenBrowser', 'StartupTimeoutSeconds')) {
        if (-not $config.ContainsKey($required)) {
            throw "本机配置缺少字段 $required。请对照 $script:OpsConfigExamplePath 修复。"
        }
    }
    if ([int]$config.StartupTimeoutSeconds -lt 5) {
        throw 'StartupTimeoutSeconds 不能小于 5。'
    }
    return $config
}

function Resolve-ConfiguredExecutable {
    param(
        [Parameter(Mandatory)][string]$ConfiguredValue,
        [Parameter(Mandatory)][string[]]$Candidates,
        [Parameter(Mandatory)][string]$DisplayName
    )

    $search = [Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($ConfiguredValue)) {
        $expanded = [Environment]::ExpandEnvironmentVariables($ConfiguredValue)
        if (-not [IO.Path]::IsPathRooted($expanded)) {
            $expanded = Join-Path $script:OpsRepositoryRoot $expanded
        }
        $search.Add($expanded)
    }
    foreach ($candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $search.Add($candidate)
        }
    }

    foreach ($candidate in $search) {
        if ([IO.Path]::IsPathRooted($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return [IO.Path]::GetFullPath($candidate)
        }
        $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }
    throw "找不到 $DisplayName。请编辑 $script:OpsConfigPath 填写绝对路径。"
}

function Get-StringSha256 {
    param([AllowEmptyString()][string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-LiveProcessIdentity {
    param([Parameter(Mandatory)][int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    $executablePath = if ($cim -and $cim.ExecutablePath) { [IO.Path]::GetFullPath($cim.ExecutablePath) } else { $process.Path }
    $commandLine = if ($cim -and $null -ne $cim.CommandLine) { [string]$cim.CommandLine } else { '' }
    return [pscustomobject]@{
        pid = $ProcessId
        executable_path = $executablePath
        process_start_utc = $process.StartTime.ToUniversalTime().ToString('o')
        command_line_sha256 = Get-StringSha256 $commandLine
    }
}

function New-ServiceIdentityRecord {
    param(
        [Parameter(Mandatory)][string]$ServiceName,
        [Parameter(Mandatory)][int]$ProcessId,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$HealthUrl,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    $identity = $null
    for ($attempt = 0; $attempt -lt 20 -and -not $identity; $attempt++) {
        Start-Sleep -Milliseconds 100
        $identity = Get-LiveProcessIdentity -ProcessId $ProcessId
    }
    if (-not $identity) {
        throw "$ServiceName 进程启动后立即退出。"
    }
    return [ordered]@{
        schema_version = 1
        service = $ServiceName
        pid = $identity.pid
        executable_path = $identity.executable_path
        process_start_utc = $identity.process_start_utc
        command_line_sha256 = $identity.command_line_sha256
        port = $Port
        health_url = $HealthUrl
        working_directory = [IO.Path]::GetFullPath($WorkingDirectory)
        managed_by = 'OPS-T04'
        recorded_at_utc = [DateTime]::UtcNow.ToString('o')
    }
}

function Test-ServiceIdentity {
    param([Parameter(Mandatory)]$Record)

    $live = Get-LiveProcessIdentity -ProcessId ([int]$Record.pid)
    if (-not $live) {
        return [pscustomobject]@{ Match = $false; Reason = '进程不存在'; Live = $null }
    }
    if (-not [string]::Equals([string]$live.executable_path, [string]$Record.executable_path, [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Match = $false; Reason = '可执行文件路径不匹配'; Live = $live }
    }
    if (-not [string]::Equals([string]$live.process_start_utc, [string]$Record.process_start_utc, [StringComparison]::Ordinal)) {
        return [pscustomobject]@{ Match = $false; Reason = '进程启动时间不匹配（PID 可能已复用）'; Live = $live }
    }
    if (-not [string]::Equals([string]$live.command_line_sha256, [string]$Record.command_line_sha256, [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Match = $false; Reason = '命令行身份哈希不匹配'; Live = $live }
    }
    return [pscustomobject]@{ Match = $true; Reason = '身份匹配'; Live = $live }
}

function Get-ServiceStatePath {
    param([Parameter(Mandatory)][string]$ServiceName)
    return Join-Path $script:OpsStateRoot "$ServiceName.json"
}

function Get-ServiceState {
    param([Parameter(Mandatory)][string]$ServiceName)
    $path = Get-ServiceStatePath -ServiceName $ServiceName
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $null
    }
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Save-ServiceState {
    param([Parameter(Mandatory)]$Record)
    $path = Get-ServiceStatePath -ServiceName ([string]$Record.service)
    $temporaryPath = "$path.tmp"
    $Record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
    Move-Item -LiteralPath $temporaryPath -Destination $path -Force
}

function Remove-ServiceState {
    param([Parameter(Mandatory)][string]$ServiceName)
    $path = Get-ServiceStatePath -ServiceName $ServiceName
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Remove-Item -LiteralPath $path -Force
    }
}

function Write-OpsAudit {
    param(
        [Parameter(Mandatory)][string]$Action,
        [Parameter(Mandatory)][string]$Outcome,
        [string]$Service = '',
        [string]$Reason = ''
    )
    Initialize-OpsRuntime
    $entry = [ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString('o')
        action = $Action
        outcome = $Outcome
        service = $Service
        reason = $Reason
        operator = [Environment]::UserName
    }
    Add-Content -LiteralPath $script:OpsAuditPath -Value ($entry | ConvertTo-Json -Compress) -Encoding UTF8
}

function Get-PortOwnerIds {
    param([Parameter(Mandatory)][int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Assert-PortAvailable {
    param([Parameter(Mandatory)][string]$ServiceName, [Parameter(Mandatory)][int]$Port)
    $ownerIds = @(Get-PortOwnerIds -Port $Port)
    if ($ownerIds.Count -gt 0) {
        throw "$ServiceName 需要端口 $Port，但该端口已被未知 PID $($ownerIds -join ', ') 占用。为避免误杀，本脚本已停止；请人工确认占用者。"
    }
}

function Test-HttpEndpoint {
    param([Parameter(Mandatory)][string]$Url, [int]$TimeoutSeconds = 3)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-HttpEndpoint {
    param(
        [Parameter(Mandatory)][string]$ServiceName,
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][int]$ProcessId,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            throw "$ServiceName 进程在健康检查通过前退出。"
        }
        if (Test-HttpEndpoint -Url $Url) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$ServiceName 在 $TimeoutSeconds 秒内未通过健康检查：$Url"
}

function ConvertTo-NativeArgument {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Value)
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory)][string]$ServiceName,
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][hashtable]$Environment,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$HealthUrl,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    $stdout = Join-Path $script:OpsLogRoot "$ServiceName.out.log"
    $stderr = Join-Path $script:OpsLogRoot "$ServiceName.err.log"
    $previous = @{}
    try {
        foreach ($name in $Environment.Keys) {
            if ($name -notmatch '^[A-Z_][A-Z0-9_]*$') {
                throw "非法环境变量名：$name"
            }
            $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, [string]$Environment[$name], 'Process')
        }
        $nativeArguments = ($Arguments | ForEach-Object { ConvertTo-NativeArgument -Value $_ }) -join ' '
        $process = Start-Process -FilePath $Executable -ArgumentList $nativeArguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    } finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
        }
    }

    $record = New-ServiceIdentityRecord -ServiceName $ServiceName -ProcessId $process.Id -Port $Port -HealthUrl $HealthUrl -WorkingDirectory $WorkingDirectory
    Save-ServiceState -Record $record
    Wait-HttpEndpoint -ServiceName $ServiceName -Url $HealthUrl -ProcessId $process.Id -TimeoutSeconds $TimeoutSeconds
    Write-OpsAudit -Action 'start' -Outcome 'success' -Service $ServiceName -Reason "PID $($process.Id) identity recorded and health check passed"
    return $record
}

function Stop-ManagedService {
    param([Parameter(Mandatory)][string]$ServiceName, [switch]$Quiet)

    $record = Get-ServiceState -ServiceName $ServiceName
    if (-not $record) {
        if (-not $Quiet) { Write-Host "$ServiceName：没有由 OPS 脚本记录的运行进程。" -ForegroundColor DarkGray }
        return [pscustomobject]@{ Success = $true; Stopped = $false; Reason = '无状态记录' }
    }
    $identity = Test-ServiceIdentity -Record $record
    if (-not $identity.Match) {
        Write-OpsAudit -Action 'stop' -Outcome 'refused' -Service $ServiceName -Reason $identity.Reason
        if (-not $identity.Live) {
            Remove-ServiceState -ServiceName $ServiceName
            if (-not $Quiet) { Write-Host "$ServiceName：进程已不存在，已清理过期记录。" -ForegroundColor Yellow }
            return [pscustomobject]@{ Success = $true; Stopped = $false; Reason = '进程已不存在' }
        }
        if (-not $Quiet) { Write-Host "$ServiceName：拒绝停止，$($identity.Reason)。" -ForegroundColor Red }
        return [pscustomobject]@{ Success = $false; Stopped = $false; Reason = $identity.Reason }
    }

    Stop-Process -Id ([int]$record.pid) -ErrorAction Stop
    try { Wait-Process -Id ([int]$record.pid) -Timeout 10 -ErrorAction Stop } catch { }
    if (Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue) {
        Write-OpsAudit -Action 'stop' -Outcome 'failed' -Service $ServiceName -Reason 'process did not exit in 10 seconds'
        if (-not $Quiet) { Write-Host "$ServiceName：停止请求后进程仍存在，未执行强制端口杀进程。" -ForegroundColor Red }
        return [pscustomobject]@{ Success = $false; Stopped = $false; Reason = '停止超时' }
    }
    Remove-ServiceState -ServiceName $ServiceName
    Write-OpsAudit -Action 'stop' -Outcome 'success' -Service $ServiceName -Reason "verified PID $($record.pid) stopped"
    if (-not $Quiet) { Write-Host "$ServiceName：已安全停止。" -ForegroundColor Green }
    return [pscustomobject]@{ Success = $true; Stopped = $true; Reason = '已停止' }
}

function Get-ManagedServiceStatus {
    param([Parameter(Mandatory)][string]$ServiceName, [Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$HealthUrl)

    $record = Get-ServiceState -ServiceName $ServiceName
    $owners = @(Get-PortOwnerIds -Port $Port)
    if (-not $record) {
        if ($owners.Count -gt 0) {
            return [pscustomobject]@{ Service = $ServiceName; State = 'UNKNOWN_PORT_OWNER'; Pid = ($owners -join ','); Port = $Port; Healthy = $false; Detail = '端口由未记录进程占用；不会自动停止' }
        }
        return [pscustomobject]@{ Service = $ServiceName; State = 'STOPPED'; Pid = ''; Port = $Port; Healthy = $false; Detail = '未启动' }
    }
    $identity = Test-ServiceIdentity -Record $record
    if (-not $identity.Match) {
        return [pscustomobject]@{ Service = $ServiceName; State = 'IDENTITY_MISMATCH'; Pid = $record.pid; Port = $Port; Healthy = $false; Detail = $identity.Reason }
    }
    $healthy = Test-HttpEndpoint -Url $HealthUrl
    return [pscustomobject]@{ Service = $ServiceName; State = if ($healthy) { 'RUNNING' } else { 'UNHEALTHY' }; Pid = $record.pid; Port = $Port; Healthy = $healthy; Detail = if ($healthy) { '身份匹配，健康检查通过' } else { '身份匹配，但健康检查失败' } }
}

function Enter-OpsLock {
    Initialize-OpsRuntime
    $path = Join-Path $script:OpsRuntimeRoot 'operation.lock'
    try {
        return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        throw '另一个启动或停止操作正在执行，请稍后再试。'
    }
}
