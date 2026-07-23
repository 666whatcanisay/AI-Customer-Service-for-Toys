[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'Ops.Common.ps1')

$lock = $null
$failed = $false
try {
    $lock = Enter-OpsLock
    foreach ($service in @('customer', 'rag', 'platform', 'ollama')) {
        $result = Stop-ManagedService -ServiceName $service
        if (-not $result.Success) { $failed = $true }
    }

    foreach ($entry in @(
        @{ Name = 'B 客服页面'; Port = 5173 },
        @{ Name = 'A RAG'; Port = 8000 },
        @{ Name = 'C 平台'; Port = 8011 }
    )) {
        $owners = @(Get-PortOwnerIds -Port $entry.Port)
        if ($owners.Count -gt 0) {
            Write-Host "$($entry.Name) 端口 $($entry.Port) 仍由 PID $($owners -join ', ') 占用；未按端口强杀。" -ForegroundColor Yellow
        }
    }
    if ($failed) {
        Write-Host '部分进程因身份不匹配或停止超时而保留，请人工检查。' -ForegroundColor Red
        exit 1
    }
    Write-Host '停止流程完成；只处理了由本脚本启动且身份匹配的进程。' -ForegroundColor Green
} catch {
    Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-OpsAudit -Action 'stop' -Outcome 'failed' -Reason $_.Exception.Message
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
