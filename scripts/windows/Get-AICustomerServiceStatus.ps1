[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Ops.Common.ps1')

try {
    Initialize-OpsRuntime
    $statuses = @(
        Get-ManagedServiceStatus -ServiceName 'platform' -Port 8011 -HealthUrl 'http://127.0.0.1:8011/health'
        Get-ManagedServiceStatus -ServiceName 'rag' -Port 8000 -HealthUrl 'http://127.0.0.1:8000/api/health'
        Get-ManagedServiceStatus -ServiceName 'customer' -Port 5173 -HealthUrl 'http://127.0.0.1:5173/'
    )
    $statuses | Format-Table Service, State, Pid, Port, Healthy, Detail -AutoSize
    $ollamaManaged = Get-ServiceState -ServiceName 'ollama'
    $ollamaHealthy = Test-HttpEndpoint -Url 'http://127.0.0.1:11434/api/tags'
    Write-Host "Ollama：$(if ($ollamaHealthy) { '健康' } else { '不可用' })；$(if ($ollamaManaged) { '由 OPS 记录' } else { '外部依赖或未启动' })"
    Write-OpsAudit -Action 'status' -Outcome $(if (@($statuses | Where-Object { -not $_.Healthy }).Count -eq 0) { 'healthy' } else { 'not-ready' }) -Reason 'local status check; no process changed'
    if (@($statuses | Where-Object { -not $_.Healthy }).Count -gt 0) { exit 1 }
    Write-Host 'AI 客服三个核心服务均健康。' -ForegroundColor Green
} catch {
    Write-Host "状态检查失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
