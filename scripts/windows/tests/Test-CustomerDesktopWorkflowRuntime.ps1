$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $scriptRoot 'common_ai_customer_service.ps1')

$config = @{
    PlatformDatabaseUrl = 'sqlite:///runtime-test.db'
    CorsAllowedOrigins = @('http://127.0.0.1:5173')
    LanCorsAllowedOrigins = 'http://192.168.1.20:5173'
    PlatformKnowledgeMaterialStorageDirectory = 'C:\runtime\knowledge-materials'
    RagPort = 18000
    ChannelAgentIntegrationEnabled = $false
    ChannelAgentServerUrl = ''
    ChannelAgentOperatorSessionReference = 'secrets\channel-agent-operator.session'
    ChannelAgentTimeoutSeconds = 5
    InternalServiceSecretReference = 'C:\runtime\internal-service.secret'
}
$environment = Get-LocalPlatformEnvironment $config

if ($environment.CHANNEL_AGENT_INTEGRATION_ENABLED -ne 'false') { throw 'Channel Agent integration must be disabled by default.' }
if ($environment.CHANNEL_AGENT_SERVER_URL -ne '') { throw 'Disabled integration must not guess a Channel Agent server.' }
if ($environment.CHANNEL_AGENT_OPERATOR_SESSION_FILE -ne 'secrets\channel-agent-operator.session') {
    throw 'Disabled integration must keep only the configured reference, not a secret value.'
}
if ($environment.CHANNEL_AGENT_TIMEOUT_SECONDS -ne '5') { throw 'Channel Agent timeout projection is incorrect.' }

$config.ChannelAgentIntegrationEnabled = $true
$config.ChannelAgentServerUrl = 'https://channel-agent.internal.example'
$config.ChannelAgentOperatorSessionReference = 'C:\runtime\channel-agent.session'
$enabled = Get-LanPlatformEnvironment $config
if ($enabled.CHANNEL_AGENT_INTEGRATION_ENABLED -ne 'true') { throw 'Enabled integration flag was not projected.' }
if ($enabled.CHANNEL_AGENT_SERVER_URL -ne 'https://channel-agent.internal.example') { throw 'Server URL was not projected.' }
if ($enabled.CHANNEL_AGENT_OPERATOR_SESSION_FILE -ne 'C:\runtime\channel-agent.session') { throw 'Session reference path was not projected.' }

Write-Host 'Customer Desktop Workflow runtime configuration tests passed.'
