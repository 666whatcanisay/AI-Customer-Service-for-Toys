Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LocalConfig {
    $configPath = Join-Path $PSScriptRoot 'config.local.ps1'
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "缺少本地配置：$configPath。请将 config.local.ps1.example 复制为 config.local.ps1 后填写。"
    }
    $config = & $configPath
    if ($null -eq $config -or -not ($config -is [hashtable])) { throw 'config.local.ps1 必须返回一个 hashtable（请以示例文件为准）。' }
    foreach ($key in @('RepositoryRoot','RagPythonPath','PlatformPythonPath','PnpmCommand','RagPort','CustomerWebPort','PlatformPort','BindAddress','CustomerWebUrl','RagHealthPath','PlatformHealthPath','OllamaModel','CorsAllowedOrigins','OpenBrowser','RuntimeDirectory','AutoImportTestData')) {
        if (-not $config.ContainsKey($key) -or $null -eq $config[$key] -or [string]::IsNullOrWhiteSpace([string]$config[$key])) { throw "配置项 $key 缺失或为空。" }
    }
    try { $root = (Resolve-Path -LiteralPath $config.RepositoryRoot -ErrorAction Stop).Path } catch { throw "RepositoryRoot 不存在：$($config.RepositoryRoot)" }
    foreach ($directory in @('backend','frontend','platform_backend')) { if (-not (Test-Path -LiteralPath (Join-Path $root $directory))) { throw "RepositoryRoot 不含 $directory：$root" } }
    $config.RepositoryRoot = $root
    if ([string]::IsNullOrWhiteSpace([string]$config.RuntimeDirectory)) { $config.RuntimeDirectory = Join-Path $root '.runtime' }
    foreach ($name in @('RagPort','CustomerWebPort','PlatformPort')) {
        $port = 0
        if (-not [int]::TryParse([string]$config[$name], [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw "$name 必须为 1-65535 的端口。" }
        $config[$name] = $port
    }
    if ((@($config.RagPort,$config.CustomerWebPort,$config.PlatformPort) | Select-Object -Unique).Count -ne 3) { throw '三个服务端口必须不同。' }
    foreach ($pathKey in @('RagPythonPath','PlatformPythonPath')) { if (-not (Test-Path -LiteralPath $config[$pathKey])) { throw "$pathKey 不存在：$($config[$pathKey])" } }
    if (-not (Get-Command $config.PnpmCommand -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $config.PnpmCommand)) { throw "PnpmCommand 不可用：$($config.PnpmCommand)" }
    if (@($config.CorsAllowedOrigins).Count -eq 0) { throw 'CorsAllowedOrigins 至少要有一个来源。' }
    return $config
}

function Get-ServiceRecordPath($Config, [string]$Name) { Join-Path $Config.RuntimeDirectory "$Name.json" }
function Get-ServiceLogDirectory($Config) { Join-Path $Config.RuntimeDirectory 'logs' }
function Get-ServiceUrl($Config, [int]$Port, [string]$Path = '/') { "http://$($Config.BindAddress):$Port$Path" }

function Get-ProcessMetadata([int]$Id) {
    Get-CimInstance Win32_Process -Filter "ProcessId = $Id" -ErrorAction SilentlyContinue
}

function Test-RecordedProcess($Config, [string]$Name, [switch]$Detailed) {
    $path = Get-ServiceRecordPath $Config $Name
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return [pscustomobject]@{ Valid = $false; Reason = '运行记录无法解析'; Record = $null; Process = $null } }
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return [pscustomobject]@{ Valid = $false; Reason = 'PID 已退出'; Record = $record; Process = $null } }
    $metadata = Get-ProcessMetadata $process.Id
    if (-not $metadata -or [string]::IsNullOrWhiteSpace($metadata.ExecutablePath)) { return [pscustomobject]@{ Valid = $false; Reason = '无法读取进程可执行路径'; Record = $record; Process = $process } }
    $sameExecutable = [string]::Equals([IO.Path]::GetFullPath($metadata.ExecutablePath), [IO.Path]::GetFullPath($record.executablePath), [StringComparison]::OrdinalIgnoreCase)
    $hasFeature = -not [string]::IsNullOrWhiteSpace($metadata.CommandLine) -and $metadata.CommandLine.IndexOf([string]$record.commandFeature, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $recordedStart = ([datetime]$record.startedUtc).ToUniversalTime().ToString('o')
    $sameStart = $process.StartTime.ToUniversalTime().ToString('o') -eq $recordedStart
    if ($sameExecutable -and $hasFeature -and $sameStart) { return [pscustomobject]@{ Valid = $true; Reason = '已验证'; Record = $record; Process = $process } }
    return [pscustomobject]@{ Valid = $false; Reason = 'PID、可执行路径、启动时间或命令特征不匹配'; Record = $record; Process = $process }
}

function Save-ServiceRecord($Config, [string]$Name, $Process, [string]$ExecutablePath, [string]$WorkingDirectory, [string]$CommandSummary, [string]$CommandFeature, [int]$Port) {
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory, (Get-ServiceLogDirectory $Config) | Out-Null
    $record = [ordered]@{ name=$Name; pid=$Process.Id; executablePath=[IO.Path]::GetFullPath($ExecutablePath); workingDirectory=[IO.Path]::GetFullPath($WorkingDirectory); startedUtc=$Process.StartTime.ToUniversalTime().ToString('o'); commandSummary=$CommandSummary; commandFeature=$CommandFeature; port=$Port; logDirectory=(Get-ServiceLogDirectory $Config) }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Get-ServiceRecordPath $Config $Name) -Encoding UTF8
}

function Get-PortOwner([int]$Port) { @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) }
function Assert-PortAvailable($Config, [string]$Name, [int]$Port) {
    $owners = Get-PortOwner $Port
    if ($owners.Count -eq 0) { return }
    $record = Test-RecordedProcess $Config $Name
    if ($record -and $record.Valid -and $owners -contains $record.Process.Id) { throw "$Name 已由本工具启动（PID $($record.Process.Id)，端口 $Port）。请使用检查脚本，或先停止后再启动。" }
    throw "端口 $Port 已被未知或未验证进程占用（PID：$($owners -join ', ')）。为避免误杀，启动已停止；请人工处理该进程。"
}

function Test-HttpOk([string]$Url) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3; return $r.StatusCode -ge 200 -and $r.StatusCode -lt 400 } catch { return $false } }
function Wait-HttpOk([string]$Url, [int]$Seconds, [string]$Label) { for ($i=0; $i -lt $Seconds; $i++) { if (Test-HttpOk $Url) { return }; Start-Sleep -Seconds 1 }; throw "$Label 未在 $Seconds 秒内就绪：$Url。请查看运行日志。" }

function Assert-Dependencies($Config) {
    foreach ($item in @(@{Name='RAG Python';Path=$Config.RagPythonPath}, @{Name='平台 Python';Path=$Config.PlatformPythonPath})) { & $item.Path --version | Out-Null; if ($LASTEXITCODE -ne 0) { throw "$($item.Name) 无法执行：$($item.Path)" } }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue; if (-not $node) { throw '缺少 Node.js（node.exe）。脚本不会自动安装。' }
    & $Config.PnpmCommand --version | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'pnpm 无法执行。脚本不会自动安装依赖。' }
    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue; if (-not $ollama) { $ollama = Get-Command ollama -ErrorAction SilentlyContinue }; if (-not $ollama) { throw '缺少 Ollama。脚本不会下载或安装模型。' }
    $models = & $ollama.Source list 2>$null; if ($LASTEXITCODE -ne 0) { throw 'Ollama 服务不可用。' }
    if (-not ($models | Where-Object { $_ -match "^$([regex]::Escape($Config.OllamaModel))\s" })) { throw "Ollama 模型不存在：$($Config.OllamaModel)。脚本不会下载模型。" }
    foreach ($path in @((Join-Path $Config.RepositoryRoot 'backend\.venv\Scripts\python.exe'), (Join-Path $Config.RepositoryRoot 'platform_backend\.venv\Scripts\python.exe'), (Join-Path $Config.RepositoryRoot 'frontend\node_modules'))) { if (-not (Test-Path -LiteralPath $path)) { throw "缺少预先安装的运行依赖：$path" } }
    if (-not (Test-Path -LiteralPath (Join-Path $Config.RepositoryRoot 'frontend\node_modules\vite\bin\vite.js'))) { throw 'frontend node_modules 中缺少 Vite。请人工安装依赖。' }
}

function Start-ManagedService($Config, [string]$Name, [string]$ExecutablePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$CommandFeature, [int]$Port) {
    Assert-PortAvailable $Config $Name $Port
    $logDir = Get-ServiceLogDirectory $Config
    New-Item -ItemType Directory -Force -Path $Config.RuntimeDirectory, $logDir | Out-Null
    $process = Start-Process -FilePath $ExecutablePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -RedirectStandardOutput (Join-Path $logDir "$Name.out.log") -RedirectStandardError (Join-Path $logDir "$Name.err.log") -WindowStyle Hidden -PassThru
    Save-ServiceRecord $Config $Name $process $ExecutablePath $WorkingDirectory (($Arguments -join ' ')) $CommandFeature $Port
    return $process
}

function Stop-ManagedService($Config, [string]$Name) {
    $path = Get-ServiceRecordPath $Config $Name
    if (-not (Test-Path -LiteralPath $path)) { Write-Host "$Name：没有本工具的运行记录。"; return }
    $check = Test-RecordedProcess $Config $Name
    if (-not $check.Process) { Remove-Item -LiteralPath $path -Force; Write-Host "$Name：记录的进程已退出，已清理记录。"; return }
    if (-not $check.Valid) { Write-Warning "$Name：拒绝停止 PID $($check.Process.Id)，原因：$($check.Reason)。请人工核对后处理。"; return }
    Stop-Process -Id $check.Process.Id -ErrorAction Stop
    Start-Sleep -Milliseconds 500
    if (Get-Process -Id $check.Process.Id -ErrorAction SilentlyContinue) { throw "$Name（PID $($check.Process.Id)）未能停止，请人工处理。" }
    Remove-Item -LiteralPath $path -Force
    Write-Host "$Name 已停止（PID $($check.Record.pid)）。"
}

function Import-TestDataPackage($Config) {
    if (-not [bool]$Config.AutoImportTestData) { return }
    if ([string]::IsNullOrWhiteSpace([string]$Config.TestDataPackagePath) -or -not (Test-Path -LiteralPath $Config.TestDataPackagePath)) { throw 'AutoImportTestData=true 时，TestDataPackagePath 必须指向存在的 ZIP 测试数据包。' }
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $form = New-Object System.Net.Http.MultipartFormDataContent
    $stream = [IO.File]::OpenRead($Config.TestDataPackagePath)
    try { $content = New-Object System.Net.Http.StreamContent($stream); $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/zip'); $form.Add($content, 'file', [IO.Path]::GetFileName($Config.TestDataPackagePath)); $response = $client.PostAsync((Get-ServiceUrl $Config $Config.PlatformPort '/api/v1/test-data-packages'), $form).GetAwaiter().GetResult(); if (-not $response.IsSuccessStatusCode) { throw "测试数据导入失败：HTTP $([int]$response.StatusCode) $($response.ReasonPhrase)" }; Write-Host '测试数据包已导入。' } finally { $stream.Dispose(); $form.Dispose(); $client.Dispose() }
}
