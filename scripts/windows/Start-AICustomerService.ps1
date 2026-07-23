[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot 'Ops.Common.ps1')

$lock = $null
$startedThisRun = [Collections.Generic.List[string]]::new()
try {
    $lock = Enter-OpsLock
    $config = Get-OpsConfig
    $timeout = [int]$config.StartupTimeoutSeconds

    $ragPython = Resolve-ConfiguredExecutable -ConfiguredValue ([string]$config.RagPython) -Candidates @(
        (Join-Path $script:OpsRepositoryRoot 'backend\.venv\Scripts\python.exe'),
        'python.exe'
    ) -DisplayName 'A 线 Python'
    $platformPython = Resolve-ConfiguredExecutable -ConfiguredValue ([string]$config.PlatformPython) -Candidates @(
        (Join-Path $script:OpsRepositoryRoot 'platform_backend\.venv\Scripts\python.exe'),
        'python.exe'
    ) -DisplayName 'C 线 Python'
    $node = Resolve-ConfiguredExecutable -ConfiguredValue ([string]$config.NodeExecutable) -Candidates @('node.exe') -DisplayName 'Node.js'

    $frontendDirectory = Join-Path $script:OpsRepositoryRoot 'frontend'
    $viteEntry = Join-Path $frontendDirectory 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
        throw "B 线依赖不存在：$viteEntry。请先在 frontend 执行 npm ci。"
    }

    & $ragPython -c 'import fastapi, uvicorn, chromadb' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'A 线 Python 缺少运行依赖，请在对应环境安装 backend/requirements.txt。' }
    & $platformPython -c 'import fastapi, uvicorn, sqlalchemy, alembic' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'C 线 Python 缺少运行依赖，请在对应环境安装 platform_backend/requirements.txt。' }

    $plan = @(
        [pscustomobject]@{ Service = 'platform'; Port = $script:OpsPorts.platform; Url = "http://127.0.0.1:$($script:OpsPorts.platform)/health" },
        [pscustomobject]@{ Service = 'rag'; Port = $script:OpsPorts.rag; Url = "http://127.0.0.1:$($script:OpsPorts.rag)/api/health" },
        [pscustomobject]@{ Service = 'customer'; Port = $script:OpsPorts.customer; Url = "http://127.0.0.1:$($script:OpsPorts.customer)/" }
    )

    foreach ($item in $plan) {
        $existing = Get-ServiceState -ServiceName $item.Service
        if ($existing) {
            $identity = Test-ServiceIdentity -Record $existing
            if ($identity.Match -and (Test-HttpEndpoint -Url $item.Url)) {
                Write-Host "$($item.Service)：已由 OPS 脚本启动且健康，继续复用。" -ForegroundColor Green
                continue
            }
            if ($identity.Live) {
                throw "$($item.Service) 存在状态记录但身份或健康状态异常：$($identity.Reason)。为避免误操作，启动已停止。"
            }
            Remove-ServiceState -ServiceName $item.Service
        }
        Assert-PortAvailable -ServiceName $item.Service -Port $item.Port
    }

    $ollamaUrl = 'http://127.0.0.1:11434/api/tags'
    if (-not (Test-HttpEndpoint -Url $ollamaUrl)) {
        $ollamaOwners = @(Get-PortOwnerIds -Port $script:OpsPorts.ollama)
        if ($ollamaOwners.Count -gt 0) {
            throw "Ollama 健康检查失败且 11434 由未知 PID $($ollamaOwners -join ', ') 占用。不会终止未知进程。"
        }
        if (-not [bool]$config.AutoStartOllama) {
            throw 'Ollama 未运行，且配置禁止自动启动。请先启动 Ollama 或设置 AutoStartOllama = $true。'
        }
        $ollama = Resolve-ConfiguredExecutable -ConfiguredValue ([string]$config.OllamaExecutable) -Candidates @('ollama.exe') -DisplayName 'Ollama'
        if ($DryRun) {
            Write-Host "[DRY RUN] 将启动 Ollama：$ollama serve"
        } else {
            [void](Start-ManagedProcess -ServiceName 'ollama' -Executable $ollama -Arguments @('serve') -WorkingDirectory $script:OpsRepositoryRoot -Environment @{} -Port $script:OpsPorts.ollama -HealthUrl $ollamaUrl -TimeoutSeconds $timeout)
            $startedThisRun.Add('ollama')
        }
    } else {
        Write-Host 'Ollama：已有健康服务，作为外部依赖复用；本脚本不会在停止时关闭它。' -ForegroundColor Green
    }

    if ($DryRun) {
        $plan | Format-Table Service, Port, Url -AutoSize
        Write-Host '[DRY RUN] 前置检查通过，未启动任何进程。' -ForegroundColor Green
        exit 0
    }

    $runtimeData = $script:OpsDataRoot.Replace('\', '/')
    $platformEnvironment = @{
        PLATFORM_ENVIRONMENT = 'test'
        DATABASE_URL = "sqlite:///$runtimeData/platform.db"
        CORS_ALLOWED_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
    }
    $ragEnvironment = @{
        HOST = '127.0.0.1'
        PORT = '8000'
        LLM_PROVIDER = 'ollama'
        LLM_BASE_URL = 'http://127.0.0.1:11434'
        PLATFORM_API_BASE_URL = 'http://127.0.0.1:8011'
        KNOWLEDGE_BASE_PATH = (Join-Path $script:OpsDataRoot 'knowledge_base')
        VECTOR_DB_PATH = (Join-Path $script:OpsDataRoot 'vector_db')
        LOG_DIR = (Join-Path $script:OpsLogRoot 'rag')
    }
    $frontendEnvironment = @{
        VITE_RAG_API_BASE_URL = 'http://127.0.0.1:8000'
        VITE_PLATFORM_API_BASE_URL = 'http://127.0.0.1:8011'
    }

    foreach ($directory in @($ragEnvironment.KNOWLEDGE_BASE_PATH, $ragEnvironment.VECTOR_DB_PATH, $ragEnvironment.LOG_DIR)) {
        [void](New-Item -ItemType Directory -Path $directory -Force)
    }

    if (-not (Get-ServiceState -ServiceName 'platform')) {
        [void](Start-ManagedProcess -ServiceName 'platform' -Executable $platformPython -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8011', '--no-access-log') -WorkingDirectory (Join-Path $script:OpsRepositoryRoot 'platform_backend') -Environment $platformEnvironment -Port 8011 -HealthUrl 'http://127.0.0.1:8011/health' -TimeoutSeconds $timeout)
        $startedThisRun.Add('platform')
    }
    if (-not (Get-ServiceState -ServiceName 'rag')) {
        [void](Start-ManagedProcess -ServiceName 'rag' -Executable $ragPython -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log') -WorkingDirectory (Join-Path $script:OpsRepositoryRoot 'backend') -Environment $ragEnvironment -Port 8000 -HealthUrl 'http://127.0.0.1:8000/api/health' -TimeoutSeconds $timeout)
        $startedThisRun.Add('rag')
    }
    if (-not (Get-ServiceState -ServiceName 'customer')) {
        [void](Start-ManagedProcess -ServiceName 'customer' -Executable $node -Arguments @($viteEntry, '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $frontendDirectory -Environment $frontendEnvironment -Port 5173 -HealthUrl 'http://127.0.0.1:5173/' -TimeoutSeconds $timeout)
        $startedThisRun.Add('customer')
    }

    Write-Host ''
    Write-Host 'AI 客服已启动：' -ForegroundColor Green
    Write-Host '  客服页面  http://127.0.0.1:5173/'
    Write-Host '  RAG 健康  http://127.0.0.1:8000/api/health'
    Write-Host '  平台健康  http://127.0.0.1:8011/health'
    Write-Host '测试数据仅供建议，禁止自动发送给真实客户。' -ForegroundColor Yellow
    if (-not $NoBrowser -and [bool]$config.OpenBrowser) {
        Start-Process 'http://127.0.0.1:5173/'
    }
} catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-OpsAudit -Action 'start' -Outcome 'failed' -Reason $_.Exception.Message
    for ($index = $startedThisRun.Count - 1; $index -ge 0; $index--) {
        [void](Stop-ManagedService -ServiceName $startedThisRun[$index] -Quiet)
    }
    Write-Host '已回滚本次新启动且身份匹配的进程；原有进程未被触碰。' -ForegroundColor Yellow
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
