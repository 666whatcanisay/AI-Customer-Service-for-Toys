[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')
try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $config = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $config $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    $serviceNames = @('admin-web','customer-web','rag','platform')
    foreach ($name in $serviceNames) { Stop-ManagedService $config $name }

    $remainingRecords = @($serviceNames | Where-Object { Test-Path -LiteralPath (Get-ServiceRecordPath $config $_) })
    $remainingPorts = @(
        foreach ($port in @($config.CustomerWebPort, $config.AdminWebPort, $config.RagPort, $config.PlatformPort)) {
            $owners = @(Get-PortOwner ([int]$port))
            if ($owners.Count -gt 0) { "${port}=PID $($owners -join ',')" }
        }
    )
    if ($remainingRecords.Count -gt 0 -or $remainingPorts.Count -gt 0) {
        throw "Stop did not complete; records=$($remainingRecords -join ','); listeners=$($remainingPorts -join ';'). No unknown process was terminated by port. Verify the records and retry."
    }
} catch { Write-Error $_; exit 1 }
