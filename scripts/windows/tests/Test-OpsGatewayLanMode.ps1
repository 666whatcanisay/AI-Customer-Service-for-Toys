$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$scriptsRoot = Join-Path $repositoryRoot 'scripts\windows'
. (Join-Path $scriptsRoot 'common_ai_customer_service.ps1')

$candidate = [pscustomobject]@{
    IPAddress = '192.168.1.11'
    InterfaceIndex = 11
    InterfaceAlias = 'Ethernet'
    InterfaceDescription = 'Physical Ethernet'
    PrefixLength = 24
    SubnetMask = '255.255.255.0'
    DefaultGateway = '192.168.1.1'
}
$privateProfile = [pscustomobject]@{
    InterfaceAlias = 'Ethernet'
    NetworkName = 'Controlled LAN'
    NetworkCategory = 'Private'
    Detail = ''
}
$config = @{
    LanAddress = 'auto'
    PreferredInterfaceAlias = ''
    AllowPublicNetwork = $false
    CustomerWebPort = 5173
    AdminWebPort = 5174
    RagPort = 8000
    PlatformPort = 8011
    BindAddress = '127.0.0.1'
    AdminWebUrl = 'http://127.0.0.1:5174/'
    CustomerWebTlsCertificateReference = 'C:\runtime\customer-web.crt'
    CustomerWebTlsKeyReference = 'C:\runtime\customer-web.key'
    GatewayLanBindAddress = 'auto'
    GatewayLanPort = 18080
    GatewayAllowedNetworks = @('auto')
    GatewayUpstreamTimeoutSeconds = 180
}

$lan = Resolve-AiCsGatewayNetworkConfig $config 'LAN' @($candidate) $privateProfile
if ($lan.GatewayNetworkMode -ne 'LAN') { throw 'Gateway LAN mode was not resolved.' }
if ($lan.BindAddress -ne '127.0.0.1') { throw 'A Core must remain loopback-only in Gateway LAN mode.' }
if ($lan.GatewayLanBindAddressResolved -ne '192.168.1.11') { throw 'Gateway LAN bind address is incorrect.' }
if ($lan.GatewayEndpointOrigin -ne 'http://192.168.1.11:18080') { throw 'Gateway LAN endpoint is incorrect.' }
if (@($lan.GatewayAllowedNetworksResolved).Count -ne 1 -or $lan.GatewayAllowedNetworksResolved[0] -ne '192.168.1.0/24') { throw 'Gateway allowed network was not resolved to the physical subnet.' }

$readyRule = {
    [pscustomobject]@{
        Enabled='True'; Direction='Inbound'; Action='Allow'; Profile='Private'; Protocol='TCP'
        LocalPort=@('18080'); LocalAddress=@('192.168.1.11'); RemoteAddress=@('192.168.1.0/255.255.255.0')
    }
}
$firewall = Get-AiCsGatewayLanFirewallReadiness $lan $readyRule
if (-not $firewall.Ready -or $firewall.State -ne 'READY') { throw 'Exact Gateway firewall rule should pass.' }

$broadRule = {
    [pscustomobject]@{
        Enabled='True'; Direction='Inbound'; Action='Allow'; Profile='Private'; Protocol='TCP'
        LocalPort=@('18080'); LocalAddress=@('Any'); RemoteAddress=@('Any')
    }
}
$broadFirewall = Get-AiCsGatewayLanFirewallReadiness $lan $broadRule
if ($broadFirewall.Ready) { throw 'Wildcard Gateway firewall rule must fail closed.' }

$missingFirewall = Get-AiCsGatewayLanFirewallReadiness $lan { @() }
if ($missingFirewall.Ready -or $missingFirewall.State -ne 'MISSING') { throw 'Missing Gateway firewall rule must fail closed.' }

$publicProfile = [pscustomobject]@{ InterfaceAlias='Ethernet'; NetworkName='Public'; NetworkCategory='Public'; Detail='' }
$publicRejected = $false
try { Resolve-AiCsGatewayNetworkConfig $config 'LAN' @($candidate) $publicProfile | Out-Null } catch { $publicRejected = $true }
if (-not $publicRejected) { throw 'Public network profile must be rejected.' }

$wideConfig = @{}
foreach ($entry in $config.GetEnumerator()) { $wideConfig[$entry.Key] = $entry.Value }
$wideConfig.GatewayAllowedNetworks = @('192.168.0.0/16')
$wideRejected = $false
try { Resolve-AiCsGatewayNetworkConfig $wideConfig 'LAN' @($candidate) $privateProfile | Out-Null } catch { $wideRejected = $true }
if (-not $wideRejected) { throw 'Allowed networks broader than the selected physical subnet must be rejected.' }

foreach ($invalid in @('0.0.0.0','8.8.8.8','198.18.0.1')) {
    if (Test-PrivateLanIpv4 $invalid) { throw "Unsafe bind address was accepted: $invalid" }
}

$startSource = Get-Content -LiteralPath (Join-Path $scriptsRoot 'start_ai_cs_server.ps1') -Raw -Encoding UTF8
foreach ($required in @('Assert-AiCsGatewayLanFirewallReady','Start-AiCsGatewayLanService','GatewayEndpointOrigin')) {
    if ($startSource -notmatch [regex]::Escape($required)) { throw "Production start wrapper is missing $required" }
}
$stopSource = Get-Content -LiteralPath (Join-Path $scriptsRoot 'stop_ai_cs_server.ps1') -Raw -Encoding UTF8
if ($stopSource -notmatch 'Stop-ManagedService.+gateway-lan') { throw 'Production stop wrapper does not stop gateway-lan.' }

Write-Host 'OPS Gateway controlled LAN mode checks: PASS'
