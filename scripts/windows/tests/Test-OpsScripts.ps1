Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("ops-t04-test-" + [Guid]::NewGuid().ToString('N'))
$env:OPS_RUNTIME_ROOT = $testRoot
try {
    . (Join-Path $PSScriptRoot '..\Ops.Common.ps1')

    if ($script:OpsPorts.rag -ne 8000 -or $script:OpsPorts.customer -ne 5173 -or $script:OpsPorts.platform -ne 8011) {
        throw '冻结端口配置不正确。'
    }
    Initialize-OpsRuntime
    if (-not (Test-Path -LiteralPath $script:OpsConfigPath -PathType Leaf)) {
        throw '未生成本机配置。'
    }
    $config = Get-OpsConfig
    if (-not $config.ContainsKey('AutoStartOllama')) {
        throw '配置字段验证失败。'
    }

    $record = New-ServiceIdentityRecord -ServiceName 'self-test' -ProcessId $PID -Port 65530 -HealthUrl 'http://127.0.0.1:65530/' -WorkingDirectory $PSScriptRoot
    $positive = Test-ServiceIdentity -Record ([pscustomobject]$record)
    if (-not $positive.Match) {
        throw "合法进程身份未通过：$($positive.Reason)"
    }
    $record.command_line_sha256 = ('0' * 64)
    $negative = Test-ServiceIdentity -Record ([pscustomobject]$record)
    if ($negative.Match -or $negative.Reason -ne '命令行身份哈希不匹配') {
        throw '篡改的进程身份未被拒绝。'
    }

    foreach ($name in @('启动AI客服.bat', '停止AI客服.bat', '检查AI客服状态.bat')) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:OpsScriptRoot $name) -PathType Leaf)) {
            throw "缺少入口：$name"
        }
    }
    Write-Host 'OPS-T04 单元/静态测试：PASS（端口冻结、配置生成、身份匹配与篡改拒绝、三个入口存在）。' -ForegroundColor Green
} finally {
    Remove-Item Env:OPS_RUNTIME_ROOT -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
