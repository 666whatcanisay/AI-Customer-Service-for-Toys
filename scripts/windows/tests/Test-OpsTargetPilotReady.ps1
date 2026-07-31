Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-target-pilot-ready-' + [Guid]::NewGuid().ToString('N'))

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function New-HealthyStatus([int]$Port) {
    return [pscustomobject]@{
        State = ([string]([char]0x8FD0) + [char]0x884C + [char]0x4E2D + [char]0xFF08 + 'RUNNING' + [char]0xFF09)
        HealthState = ([string]([char]0x53EF) + [char]0x7528)
        ManagedProcessId = '101'
        ListenerProcessId = '102'
        Port = $Port
        PortState = 'LISTENING'
        Record = [pscustomobject]@{ Valid = $true }
    }
}

function New-ServiceStatuses([int]$CustomerPort, [int]$AdminPort) {
    return @(
        [pscustomobject]@{ Label='C'; Status=(New-HealthyStatus 18011) },
        [pscustomobject]@{ Label='A'; Status=(New-HealthyStatus 18000) },
        [pscustomobject]@{ Label='B'; Status=(New-HealthyStatus $CustomerPort) },
        [pscustomobject]@{ Label='Admin'; Status=(New-HealthyStatus $AdminPort) }
    )
}

try {
    $scriptPaths = @(
        'scripts\windows\common_ai_customer_service.ps1',
        'scripts\windows\start_ai_customer_service.ps1',
        'scripts\windows\check_target_pilot_readiness.ps1',
        'scripts\windows\start_target_pilot.ps1',
        'scripts\windows\recover_target_pilot.ps1',
        'scripts\windows\test_customer_pilot_access.ps1',
        'scripts\windows\test_target_pilot_component_recovery.ps1',
        'scripts\windows\backup_target_pilot_data.ps1',
        'scripts\windows\stop_ai_customer_service.ps1'
    )
    foreach ($path in $scriptPaths) {
        $tokens = $null
        $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $repositoryRoot $path), [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "$path has a PowerShell syntax error: $($errors[0].Message)" }
    }

    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $customerPort = Get-AvailableLoopbackPort
    $adminPort = Get-AvailableLoopbackPort
    $healthyHttpProbe = { param([string]$Url) [pscustomobject]@{ Url=$Url; Reachable=$true; StatusCode=200 } }
    $healthyTcpProbe = { param([string]$TargetHost, [int]$Port) $true }

    $config = @{
        RuntimeDirectory = (Join-Path $temporaryRoot 'runtime')
        CustomerWebUrl = "http://127.0.0.1:$customerPort/"
        CustomerWebPort = $customerPort
        AdminWebUrl = "http://127.0.0.1:$adminPort/"
        AdminWebPort = $adminPort
        AdminWebBindAddress = '127.0.0.1'
        AdminEnableLanMode = $false
    }
    $healthyStatuses = New-ServiceStatuses $customerPort $adminPort
    $localReadiness = Get-TargetPilotReadiness $config -Mode Local -ServiceStatuses $healthyStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe
    if (-not $localReadiness.Ready -or $localReadiness.State -ne 'READY_FOR_CUSTOMER_PILOT') { throw "Expected local READY state, received $($localReadiness.State)." }
    if (-not $localReadiness.Probes.TcpReachable -or -not $localReadiness.Probes.CustomerPage.Reachable -or -not $localReadiness.Probes.RagProxy.Reachable -or -not $localReadiness.Probes.PlatformProxy.Reachable) { throw 'The customer page or fixed proxy probes did not pass.' }
    if ($localReadiness.SimulationScope -notmatch 'server-local endpoint probe') { throw 'The local simulation scope was not recorded.' }

    $reportPath = Save-TargetPilotReadinessReport $config $localReadiness
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.schemaVersion -ne 'target-pilot-readiness.v1' -or $report.state -ne 'READY_FOR_CUSTOMER_PILOT' -or -not $report.ready) { throw 'The readiness report does not contain the expected safe result.' }
    $reportText = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8
    if ($reportText -match '(?i)(password|token|secret|commandline|configuration)') { throw 'The readiness report contains an unsafe field name.' }

    $unreadyStatuses = New-ServiceStatuses $customerPort $adminPort
    $unreadyStatuses[0].Status.State = 'NOT_RUNNING'
    $unready = Get-TargetPilotReadiness $config -Mode Local -ServiceStatuses $unreadyStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe
    if ($unready.State -ne 'SERVICE_NOT_READY' -or $unready.ServiceFailures -notcontains 'C') { throw 'A missing trusted service was not classified safely.' }

    $exposedAdminConfig = @{}
    foreach ($entry in $config.GetEnumerator()) { $exposedAdminConfig[$entry.Key] = $entry.Value }
    $exposedAdminConfig.AdminEnableLanMode = $true
    $exposedAdminConfig.AdminWebBindAddress = '0.0.0.0'
    $adminBlocked = Get-TargetPilotReadiness $exposedAdminConfig -Mode Local -ServiceStatuses $healthyStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe
    if ($adminBlocked.State -ne 'ADMIN_LOOPBACK_REQUIRED') { throw 'Admin LAN exposure was not blocked by readiness.' }

    $lanBlocked = Get-TargetPilotReadiness $config -Mode Lan -ServiceStatuses $healthyStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe
    if ($lanBlocked.State -ne 'LAN_CONFIGURATION_REQUIRED') { throw 'A loopback-only customer URL was accepted as a LAN pilot.' }
    if ($lanBlocked.SimulationScope -notmatch 'second customer computer') { throw 'The server-side LAN simulation limitation was not recorded.' }

    $lanConfig = @{}
    foreach ($entry in $config.GetEnumerator()) { $lanConfig[$entry.Key] = $entry.Value }
    $lanConfig.CustomerWebUrl = 'http://192.168.1.20:5173/'
    $lanConfig.CustomerWebPort = 5173
    $lanConfig.CustomerWebBindAddress = '192.168.1.20'
    $lanConfig.LanSelection = [pscustomobject]@{ InterfaceAlias='Private Ethernet'; IPAddress='192.168.1.20' }
    $lanConfig.LanNetworkProfile = [pscustomobject]@{ NetworkCategory='Private' }
    $lanConfig.LanSubnet = '192.168.1.0/24'
    $lanStatuses = New-ServiceStatuses 5173 $adminPort
    $firewallMissing = [pscustomobject]@{ State='FIREWALL_RULE_NOT_CONFIGURED'; Ready=$false; ExpectedPort=5173; ExpectedSubnet='192.168.1.0/24' }
    $firewallBlocked = Get-TargetPilotReadiness $lanConfig -Mode Lan -ServiceStatuses $lanStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe -FirewallReadiness $firewallMissing
    if ($firewallBlocked.State -ne 'FIREWALL_CONFIGURATION_REQUIRED') { throw 'A LAN pilot without the scoped firewall rule was accepted.' }
    $mockFirewallRule = [pscustomobject]@{ Enabled='True'; Direction='Inbound'; Action='Allow'; Profile='Private' }
    function Get-NetFirewallPortFilter { param($AssociatedNetFirewallRule) [pscustomobject]@{ Protocol='TCP'; LocalPort='5173' } }
    function Get-NetFirewallAddressFilter { param($AssociatedNetFirewallRule) [pscustomobject]@{ RemoteAddress='192.168.1.0/24' } }
    $computedFirewallReady = Get-TargetPilotFirewallReadiness $lanConfig { @($mockFirewallRule) }
    if (-not $computedFirewallReady.Ready -or $computedFirewallReady.State -ne 'SCOPED_5173_PRIVATE_RULE_PRESENT') { throw 'The scoped Private TCP 5173 firewall rule was not recognised.' }
    $firewallReady = [pscustomobject]@{ State='SCOPED_5173_PRIVATE_RULE_PRESENT'; Ready=$true; ExpectedPort=5173; ExpectedSubnet='192.168.1.0/24' }
    $lanReady = Get-TargetPilotReadiness $lanConfig -Mode Lan -ServiceStatuses $lanStatuses -HttpProbe $healthyHttpProbe -TcpProbe $healthyTcpProbe -FirewallReadiness $firewallReady
    if (-not $lanReady.Ready -or $lanReady.Firewall.State -ne 'SCOPED_5173_PRIVATE_RULE_PRESENT') { throw 'A valid scoped firewall gate did not produce LAN readiness.' }

    $clientReady = Get-TargetPilotCustomerAccess '192.168.1.20' 5173 $healthyHttpProbe $healthyTcpProbe
    if (-not $clientReady.Ready -or $clientReady.State -ne 'READY_FOR_CUSTOMER_ACCESS') { throw 'The second-computer customer access check did not validate the fixed proxies.' }
    $clientRejected = Get-TargetPilotCustomerAccess '127.0.0.1' 5173 $healthyHttpProbe $healthyTcpProbe
    if ($clientRejected.State -ne 'UNSAFE_SERVER_ADDRESS') { throw 'The customer access check accepted a loopback server address.' }

    Add-TargetPilotOpsEvent $config 'READINESS' 'READY' $lanReady @('A','B','C')
    $eventText = Get-Content -LiteralPath (Get-TargetPilotOpsEventPath $config) -Raw -Encoding UTF8
    if ($eventText -notmatch 'target-pilot-ops-event.v1' -or $eventText -match '(?i)"(password|token|secret|commandline|configuration)"\s*:') { throw 'The pilot event log is missing or contains an unsafe field name.' }

    $batchContents = @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'scripts\windows') -Filter '*.bat' -File | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw })
    foreach ($entryPoint in @('start_target_pilot.ps1','check_target_pilot_readiness.ps1','recover_target_pilot.ps1','test_customer_pilot_access.ps1','test_target_pilot_component_recovery.ps1','backup_target_pilot_data.ps1')) {
        if (@($batchContents | Where-Object { $_.Contains($entryPoint) }).Count -ne 1) { throw "Missing or ambiguous pilot batch entry: $entryPoint" }
    }
    $recoveryScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\recover_target_pilot.ps1') -Raw
    $stopScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\stop_ai_customer_service.ps1') -Raw
    $componentRecoveryScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\test_target_pilot_component_recovery.ps1') -Raw
    $backupScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\backup_target_pilot_data.ps1') -Raw
    $targetPilotStartScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\start_target_pilot.ps1') -Raw
    if ($recoveryScript -notmatch 'ConfirmRestart' -or $recoveryScript -notmatch 'AllowFirewallGate' -or $recoveryScript -match 'Stop-Process' -or $stopScript -notmatch 'Get-LocalConfig \$ConfigPath' -or $componentRecoveryScript -notmatch 'ConfirmDisruption' -or $componentRecoveryScript -match 'Stop-Process' -or $backupScript -notmatch 'ConfirmBackup' -or $backupScript -notmatch 'source_db.backup') { throw 'Recovery confirmation, backup, config forwarding, or managed-stop boundary is missing.' }
    if ($targetPilotStartScript -notmatch 'start_ai_customer_service\.ps1' -or $targetPilotStartScript -match 'start_lan_ai_customer_service\.ps1' -or $targetPilotStartScript -notmatch '-Mode \$Mode' -or $targetPilotStartScript -notmatch '\$readinessMode') { throw 'Target pilot does not preserve the standard entry and selected network mode.' }
    $newScriptText = @($scriptPaths | ForEach-Object { Get-Content -LiteralPath (Join-Path $repositoryRoot $_) -Raw }) -join "`n"
    $commonScriptText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1') -Raw
    if ($newScriptText -notmatch 'NoBrowser' -or $newScriptText -match '(?i)(pnpm\s+install|Set-NetFirewall|New-NetFirewall|netsh\s+advfirewall)' -or $commonScriptText -match 'Get-NetTCPConnection') { throw 'Pilot scripts do not preserve the browser, listener-query, dependency, or firewall boundary.' }

    Write-Host 'OPS target-pilot readiness tests passed (daily wrapper, trusted health state, server-side customer simulation, report privacy, admin loopback, LAN guard, and explicit recovery).' -ForegroundColor Green
} finally {
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd([char]92)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
