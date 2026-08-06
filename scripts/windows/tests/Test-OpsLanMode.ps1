Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('ops-lan-batch-05-' + [Guid]::NewGuid().ToString('N'))
$fakeProcesses = @()

function Assert-Throws([scriptblock]$Action, [string]$Label) { try { & $Action } catch { return }; throw "$Label should fail but did not." }
function New-LanCandidate([string]$Address, [string]$Alias = 'Wi-Fi', [int]$Index = 17, [int]$Prefix = 24) {
    [pscustomobject]@{ IPAddress=$Address; InterfaceIndex=$Index; InterfaceAlias=$Alias; InterfaceDescription=$Alias; PrefixLength=$Prefix; SubnetMask='255.255.255.0'; DefaultGateway=($Address -replace '\d+$', '1') }
}
function New-NetworkProfile([string]$Category = 'Private') { [pscustomobject]@{ InterfaceAlias='Wi-Fi'; NetworkName='Office'; NetworkCategory=$Category; Detail='' } }

try {
    foreach ($path in @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'scripts\windows') -Recurse -Filter '*.ps1' | Select-Object -ExpandProperty FullName)) {
        $tokens = $null; $errors = $null; [void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) { throw "$path syntax error: $($errors[0].Message)" }
    }
    $batchFiles = @(Get-ChildItem -LiteralPath (Join-Path $repositoryRoot 'scripts\windows') -Filter '*.bat' | Select-Object -ExpandProperty Name)
    if ($batchFiles.Count -lt 9) { throw 'Expected local, LAN, firewall, and diagnostic batch entry points are missing.' }
    . (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1')

    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    $temporaryRepository = Join-Path $temporaryRoot 'repository'
    New-Item -ItemType Directory -Force -Path @((Join-Path $temporaryRepository 'backend'), (Join-Path $temporaryRepository 'frontend'), (Join-Path $temporaryRepository 'platform_backend')) | Out-Null
    $ragPython = Join-Path $temporaryRepository 'rag.exe'; $platformPython = Join-Path $temporaryRepository 'platform.exe'; New-Item -ItemType File -Path $ragPython, $platformPython | Out-Null
    $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source; $configPath = Join-Path $temporaryRoot 'config.local.ps1'
    $internalSecretPath = Join-Path $temporaryRoot 'runtime\secrets\internal-service.secret'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $internalSecretPath) | Out-Null
    [IO.File]::WriteAllText($internalSecretPath, ('i' * 32), [Text.UTF8Encoding]::new($false))
    @"
@{
RepositoryRoot = '$($temporaryRepository.Replace("'", "''"))'
RagPythonPath = '$($ragPython.Replace("'", "''"))'
PlatformPythonPath = '$($platformPython.Replace("'", "''"))'
PnpmCommand = '$($shellPath.Replace("'", "''"))'
RagPort = 18000; CustomerWebPort = 15173; PlatformPort = 18011; BindAddress = '127.0.0.1'; CustomerWebUrl = 'http://127.0.0.1:15173/'
RagHealthPath = '/api/health'; PlatformHealthPath = '/health'; OllamaModel = 'qwen3.5:9b'; CorsAllowedOrigins = @('http://127.0.0.1:15173'); OpenBrowser = `$false
RuntimeDirectory = '$((Join-Path $temporaryRoot 'runtime').Replace("'", "''"))'; TestDataPackagePath = ''; AutoImportTestData = `$false
InternalServiceSecretReference = '$($internalSecretPath.Replace("'", "''"))'
CustomerWebTlsCertificateReference = 'secrets\customer-web.crt'
CustomerWebTlsKeyReference = 'secrets\customer-web.key'
LanAddress = 'auto'; PreferredInterfaceAlias = ''; EnableLanMode = `$false
}
"@ | Set-Content -LiteralPath $configPath -Encoding UTF8

    $config = Get-LocalConfig $configPath
    if ($config.LanAddress -ne 'auto' -or $config.PreferredInterfaceAlias -ne '' -or $config.EnableLanMode) { throw 'LAN automatic defaults are incorrect.' }
    foreach ($invalidIp in @('127.0.0.1','169.254.1.10','198.18.1.10','8.8.8.8','0.0.0.0','not-an-ip')) { if (Test-PrivateLanIpv4 $invalidIp) { throw "Invalid LAN IP accepted: $invalidIp" } }
    if (-not (Test-PrivateLanIpv4 '192.168.1.20')) { throw 'Private IPv4 was rejected.' }
    if (Test-LanAdapterEligible ([pscustomobject]@{Status='Up';Name='Tailscale';InterfaceDescription='Tailscale Tunnel'})) { throw 'VPN was not excluded.' }
    if (Test-LanAdapterEligible ([pscustomobject]@{Status='Up';Name='vEthernet';InterfaceDescription='Hyper-V Virtual Ethernet'})) { throw 'Virtual adapter was not excluded.' }
    function Get-NetAdapter { [pscustomobject]@{ Status='Up'; Name='Ethernet'; InterfaceDescription='Physical Ethernet'; ifIndex=77; HardwareInterface=$true } }
    function Get-NetIPConfiguration { [pscustomobject]@{ IPv4DefaultGateway=[pscustomobject]@{ NextHop='10.77.0.1' } } }
    function Get-NetIPAddress { [pscustomobject]@{ IPAddress='10.77.0.20'; PrefixLength=24 } }
    $singleGatewayCandidates = @(Get-LanIpv4Candidates -UseLegacyPowerShellDiscovery)
    if ($singleGatewayCandidates.Count -ne 1 -or $singleGatewayCandidates[0].DefaultGateway -ne '10.77.0.1') { throw 'A single default gateway must produce one LAN candidate.' }

    $wifi = New-LanCandidate '192.168.1.20' 'Wi-Fi' 17; $ethernet = New-LanCandidate '10.20.30.40' 'Ethernet' 9; $privateProfile = New-NetworkProfile 'Private'
    $lanConfig = Resolve-LanRuntimeConfig $config @($wifi, $ethernet) $privateProfile
    if ($lanConfig.LanSelection.InterfaceAlias -ne 'Ethernet' -or $lanConfig.CustomerWebBindAddress -ne '10.20.30.40' -or $lanConfig.CustomerWebUrl -ne 'https://10.20.30.40:15173/') { throw 'Ethernet/TLS LAN endpoint resolution is incorrect.' }
    if ($lanConfig.RagBindAddress -ne '127.0.0.1' -or $lanConfig.PlatformBindAddress -ne '127.0.0.1' -or (Get-LanServiceListenerAddress $lanConfig $lanConfig.CustomerWebPort) -ne '10.20.30.40:15173') { throw 'Listener boundary is incorrect.' }
    if ($lanConfig.LanSubnet -ne '10.20.30.0/24') { throw 'Subnet calculation is incorrect.' }
    $lanCorsOrigins = @([string]$lanConfig.LanCorsAllowedOrigins -split ',')
    foreach ($requiredOrigin in @(
        'https://10.20.30.40:15173',
        'https://127.0.0.1:15173',
        'http://127.0.0.1:5174',
        'http://localhost:5174'
    )) {
        if ($requiredOrigin -notin $lanCorsOrigins) { throw "LAN CORS is missing: $requiredOrigin" }
    }
    if ('http://10.20.30.40:5174' -in $lanCorsOrigins) { throw 'Admin must remain loopback-only in LAN mode.' }
    if ((Resolve-LanRuntimeConfig $config @($wifi) $privateProfile).LanSelection.InterfaceAlias -ne 'Wi-Fi') { throw 'WLAN selection failed.' }
    if ((Resolve-LanRuntimeConfig $config @((New-LanCandidate '192.168.50.20' 'Wi-Fi' 17)) $privateProfile).LanAdvertisedHost -ne '192.168.50.20') { throw 'Changed IP was not selected.' }
    Assert-Throws { Resolve-LanRuntimeConfig $config @($ethernet, (New-LanCandidate '10.20.40.40' 'Ethernet 2' 10)) $privateProfile | Out-Null } 'Ambiguous physical adapters'
    $config.PreferredInterfaceAlias = 'Ethernet 2'; if ((Resolve-LanRuntimeConfig $config @($ethernet, (New-LanCandidate '10.20.40.40' 'Ethernet 2' 10)) $privateProfile).LanAdvertisedHost -ne '10.20.40.40') { throw 'PreferredInterfaceAlias was not honored.' }; $config.PreferredInterfaceAlias = ''
    Assert-Throws { Resolve-LanRuntimeConfig $config @($wifi) (New-NetworkProfile 'Public') | Out-Null } 'Public network protection'
    $missingTls = @{}; foreach ($entry in $config.GetEnumerator()) { $missingTls[$entry.Key] = $entry.Value }; $missingTls.CustomerWebTlsCertificateReference = ''; $missingTls.CustomerWebTlsKeyReference = ''
    Assert-Throws { Resolve-LanRuntimeConfig $missingTls @($wifi) $privateProfile | Out-Null } 'Missing LAN TLS protection'

    $lanConfig = Resolve-LanRuntimeConfig $config @($wifi) $privateProfile; $frontendEnvironment = Get-LanFrontendEnvironment $lanConfig
    if ($frontendEnvironment.VITE_RAG_API_BASE_URL -ne '/rag-api' -or $frontendEnvironment.VITE_PLATFORM_API_BASE_URL -ne '/platform-api' -or $frontendEnvironment.VITE_API_MODE -ne 'SAME_ORIGIN_PROXY') { throw 'Same-origin frontend environment is incorrect.' }
    $runtimeCommon = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\common_ai_customer_service.ps1') -Raw
    foreach ($required in @('"/rag-api=http://127.0.0.1:', '"/platform-api=http://127.0.0.1:', 'serve_ai_cs_web.py')) { if ($runtimeCommon.IndexOf($required, [StringComparison]::Ordinal) -lt 0) { throw "Production web proxy is missing: $required" } }
    if ($runtimeCommon -match '(?i)pnpm\s+(run\s+)?dev|vite\s+--host') { throw 'Production runtime must not launch Vite dev server.' }
    $ui = Get-Content -LiteralPath (Join-Path $repositoryRoot 'frontend\src\views\AiChat.vue') -Raw
    if ($ui -match '@media \(max-width: 900px\), \(max-height: 740px\)') { throw 'Height must not trigger single column.' }
    if ($ui -notmatch '@media \(min-width: 901px\)') { throw 'Desktop two-column media rule is missing.' }
    $firewallScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\configure_ai_customer_firewall.ps1') -Raw
    foreach ($required in @('Test-AICustomerServiceAdministrator','-LocalPort 5173','-Profile Private','-RemoteAddress $config.LanSubnet','CONFIGURE')) { if ($firewallScript.IndexOf($required, [StringComparison]::Ordinal) -lt 0) { throw "Firewall safeguard is missing: $required" } }
    $diagnosticScript = Get-Content -LiteralPath (Join-Path $repositoryRoot 'scripts\windows\diagnose_lan_ai_customer_service.ps1') -Raw
    if ($diagnosticScript -match '=\(if\s*\(') { throw 'LAN diagnostic report values must not invoke if as a command.' }
    foreach ($startScript in @('start_ai_customer_service.ps1','start_lan_ai_customer_service.ps1')) {
        $content = Get-Content -LiteralPath (Join-Path $repositoryRoot "scripts\windows\$startScript") -Raw
        if ($content.IndexOf('Test-ManagedServiceRunning', [StringComparison]::Ordinal) -lt 0) { throw "Trusted repeat-start protection is missing from $startScript" }
    }

    $managedPort = 55173; $command = '$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $managedPort + '); $listener.Start(); Start-Sleep -Seconds 30'
    $managedProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',$command) -WindowStyle Hidden -PassThru; $fakeProcesses += $managedProcess; Start-Sleep -Milliseconds 300
    Save-ServiceRecord $lanConfig 'customer-web' $managedProcess $shellPath $temporaryRoot 'managed listener' 'TcpListener' $managedPort
    $record = Get-Content -LiteralPath (Get-ServiceRecordPath $lanConfig 'customer-web') -Raw | ConvertFrom-Json
    foreach ($field in @('name','pid','parentProcessId','startedUtc','executablePath','workingDirectory','commandFeature','port','healthUrl')) { if ($record.PSObject.Properties.Name -notcontains $field) { throw "Runtime record is missing $field" } }
    Assert-Throws { Assert-PortAvailable $lanConfig 'customer-web' $managedPort } 'Repeated LAN startup protection'
    Stop-ManagedService $lanConfig 'customer-web' | Out-Null; if (Get-Process -Id $managedProcess.Id -ErrorAction SilentlyContinue) { throw 'Trusted service did not stop.' }; $fakeProcesses = @($fakeProcesses | Where-Object { $_.Id -ne $managedProcess.Id })
    $unknownPort = 55174; $unknownProcess = Start-Process -FilePath $shellPath -ArgumentList @('-NoProfile','-Command',('$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, ' + $unknownPort + '); $listener.Start(); Start-Sleep -Seconds 30')) -WindowStyle Hidden -PassThru; $fakeProcesses += $unknownProcess; Start-Sleep -Milliseconds 300
    Assert-Throws { Assert-PortAvailable $lanConfig 'rag' $unknownPort } 'Unknown port owner protection'; if (-not (Get-Process -Id $unknownProcess.Id -ErrorAction SilentlyContinue)) { throw 'Unknown process was stopped.' }
    Write-Host 'MVP-BATCH-05 OPS test: PASS.' -ForegroundColor Green
} finally {
    foreach ($process in $fakeProcesses) { if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } }
    if ((Test-Path -LiteralPath $temporaryRoot) -and (Split-Path -Parent $temporaryRoot) -eq [IO.Path]::GetTempPath().TrimEnd('\')) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
}
