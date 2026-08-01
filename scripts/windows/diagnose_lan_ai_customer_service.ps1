[CmdletBinding()]
param([string]$ConfigPath)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

function Protect-CommandLine([string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return '' }
    return $CommandLine -replace '(?i)(password|token|secret|api[_-]?key)(=|\s+)([^\s;]+)', '$1$2<redacted>'
}

function Get-ProcessDiagnostic([int]$ProcessId) {
    $metadata = Get-ProcessMetadata $ProcessId
    if ($null -eq $metadata) { return [pscustomobject]@{ pid=$ProcessId; found=$false } }
    $owner = ''
    try {
        $ownerResult = Invoke-CimMethod -InputObject $metadata -MethodName GetOwner -ErrorAction Stop
        if ($ownerResult.ReturnValue -eq 0) { $owner = "$($ownerResult.Domain)\\$($ownerResult.User)" }
    } catch { $owner = '<unavailable>' }
    return [pscustomobject]@{ pid=[int]$metadata.ProcessId; parentPid=[int]$metadata.ParentProcessId; executablePath=[string]$metadata.ExecutablePath; commandLine=(Protect-CommandLine ([string]$metadata.CommandLine)); creationDate=[string]$metadata.CreationDate; owner=$owner; found=$true }
}

function Get-ServiceDiagnostic($Config, [string]$Name, [int]$Port) {
    $recordPath = Get-ServiceRecordPath $Config $Name
    $record = $null; $recordError = ''
    if (Test-Path -LiteralPath $recordPath) { try { $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $recordError = $_.Exception.Message } }
    $listener = @(Get-TcpListeningConnection $Port | Select-Object LocalAddress, LocalPort, OwningProcess)
    $pids = @($listener.OwningProcess); if ($record) { $pids += [int]$record.pid }
    $healthUrl = Get-ManagedServiceHealthUrl $Config $Name
    return [pscustomobject]@{ name=$Name; port=$Port; recordPath=$recordPath; record=$record; recordError=$recordError; listeners=$listener; processes=@($pids | Select-Object -Unique | ForEach-Object { Get-ProcessDiagnostic ([int]$_) }); healthUrl=$healthUrl; healthOk=(Test-HttpOk $healthUrl) }
}

try {
    $resolvedConfigPath = Resolve-AiCustomerServiceConfigPath $ConfigPath
    $baseConfig = Get-LocalConfig $resolvedConfigPath
    Assert-AiCsCanonicalRuntimeSource $baseConfig $resolvedConfigPath -RequireCanonicalRoot:([string]::IsNullOrWhiteSpace($ConfigPath))
    $config = $baseConfig; $resolutionError = ''
    try { $config = Resolve-LanRuntimeConfig $baseConfig $null $null -SkipPublicNetworkGuard } catch { $resolutionError = $_.Exception.Message }
    $candidates = @()
    try { $candidates = @(Get-LanIpv4Candidates) } catch { $resolutionError = if ($resolutionError) { "$resolutionError; $($_.Exception.Message)" } else { $_.Exception.Message } }
    $adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Select-Object Name, InterfaceDescription, Status, ifIndex, HardwareInterface)
    $vpnOrVirtualAdapters = @($adapters | Where-Object { ("$($_.Name) $($_.InterfaceDescription)") -match '(?i)(vpn|tun|tap|wireguard|tailscale|zerotier|virtual|hyper-v|vethernet|wsl|docker)' })
    $defaultRoutes = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object InterfaceIndex, NextHop, RouteMetric, ifMetric, State)
    $rules = @()
    foreach ($rule in @(Get-AICustomerFirewallRules)) {
        $rules += [pscustomobject]@{ displayName=$rule.DisplayName; enabled=$rule.Enabled; profile=$rule.Profile; direction=$rule.Direction; action=$rule.Action; localPort=(Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule).LocalPort; remoteAddress=(Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule).RemoteAddress }
    }
    $hasLanSelection = $config.ContainsKey('LanSelection')
    $selectedAdapter = if ($hasLanSelection) { $config.LanSelection } else { $null }
    $customerUrl = if ($hasLanSelection) { [string]$config.CustomerWebUrl } else { '' }
    $clientTestCommand = if ($customerUrl) { "Test-NetConnection $($config.LanAdvertisedHost) -Port 5173" } else { '' }
    $adminDirectory = Join-Path $config.RepositoryRoot 'admin_web'
    $adminDependencies = [ordered]@{
        directoryExists = (Test-Path -LiteralPath $adminDirectory -PathType Container)
        packageJsonExists = (Test-Path -LiteralPath (Join-Path $adminDirectory 'package.json') -PathType Leaf)
        lockFileExists = (Test-Path -LiteralPath (Join-Path $adminDirectory 'pnpm-lock.yaml') -PathType Leaf)
        nodeModulesExists = (Test-Path -LiteralPath (Join-Path $adminDirectory 'node_modules') -PathType Container)
    }
    $report = [ordered]@{
        generatedUtc=[DateTime]::UtcNow.ToString('o'); diagnosticMode='read-only'; lanResolutionError=$resolutionError; selectedAdapter=$selectedAdapter; eligiblePhysicalAdapters=$candidates; vpnOrVirtualAdapters=$vpnOrVirtualAdapters; defaultRoutes=$defaultRoutes; customerUrl=$customerUrl; clientTestCommand=$clientTestCommand; adminWeb=[ordered]@{ url=[string]$config.AdminWebUrl; bindAddress=[string]$config.AdminWebBindAddress; port=[int]$config.AdminWebPort; lanEnabled=[bool]$config.AdminEnableLanMode; dependencies=$adminDependencies }; services=@((Get-ServiceDiagnostic $config 'platform' $config.PlatformPort), (Get-ServiceDiagnostic $config 'rag' $config.RagPort), (Get-ServiceDiagnostic $config 'customer-web' $config.CustomerWebPort), (Get-ServiceDiagnostic $config 'admin-web' $config.AdminWebPort)); firewallRules=$rules
    }
    $directory = Join-Path $config.RuntimeDirectory 'diagnostics'; New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $path = Join-Path $directory ("lan-diagnostic-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    Write-Host "LAN diagnostic completed (read-only): $path" -ForegroundColor Green
    if ($resolutionError) { Write-Host "LAN address resolution failed: $resolutionError" -ForegroundColor Yellow } else {
        Write-Host "Physical adapter: $($config.LanSelection.InterfaceAlias); IPv4: $($config.LanSelection.IPAddress); mask: $($config.LanSelection.SubnetMask); gateway: $($config.LanSelection.DefaultGateway)"
        Write-Host "Customer URL: $customerUrl"
        Write-Host "Run on client: Test-NetConnection $($config.LanAdvertisedHost) -Port 5173"
    }
    Write-Host "VPN/virtual adapters: $(if ($vpnOrVirtualAdapters.Count -gt 0) { ($vpnOrVirtualAdapters.Name -join ', ') } else { 'none detected' })"
    Write-Host "Admin URL: $($config.AdminWebUrl); bind=$($config.AdminWebBindAddress):$($config.AdminWebPort); LAN=$($config.AdminEnableLanMode); dependencies package=$($adminDependencies.packageJsonExists), lock=$($adminDependencies.lockFileExists), node_modules=$($adminDependencies.nodeModulesExists)"
    foreach ($service in $report.services) {
        $addresses = @($service.listeners | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) (PID $($_.OwningProcess))" }) -join '; '
        Write-Host "$($service.name): listener=$addresses; health=$($service.healthOk)"
    }
} catch { Write-Error $_; exit 1 }
