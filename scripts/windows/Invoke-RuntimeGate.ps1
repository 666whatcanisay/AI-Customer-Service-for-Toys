[CmdletBinding()]
param(
    [ValidateSet('Preflight', 'Snapshot', 'Verify')]
    [string]$Action = 'Verify',
    [string]$ConfigPath,
    [string]$RepositoryRoot,
    [string]$RuntimeDirectory,
    [int]$RagPort = 0,
    [int]$CustomerWebPort = 0,
    [int]$AdminWebPort = 0,
    [string]$CustomerWebUrl,
    [string]$AdminWebUrl,
    [string]$ExpectedGitShortSha,
    [switch]$LanMode,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

function Get-RuntimeGitIdentity([string]$Directory) {
    if ([string]::IsNullOrWhiteSpace($Directory) -or -not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return [pscustomobject]@{ Directory = $Directory; GitShortSha = $null; SourceState = 'UNAVAILABLE' }
    }
    try {
        $sha = (& git -C $Directory rev-parse --short=12 HEAD 2>$null | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sha)) { throw 'git rev-parse failed' }
        $status = & git -C $Directory status --porcelain --untracked-files=all 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
        return [pscustomobject]@{ Directory = [IO.Path]::GetFullPath($Directory); GitShortSha = $sha; SourceState = if (@($status).Count -gt 0) { 'DIRTY' } else { 'CLEAN' } }
    } catch {
        return [pscustomobject]@{ Directory = [IO.Path]::GetFullPath($Directory); GitShortSha = $null; SourceState = 'UNAVAILABLE' }
    }
}

function Get-PackageVersion([string]$Directory) {
    try {
        $package = Get-Content -LiteralPath (Join-Path $Directory 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $value = [string]$package.version
        if ([string]::IsNullOrWhiteSpace($value)) { return $null }
        return $value
    } catch { return $null }
}

function Get-ResponseText([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10 -ErrorAction Stop
        return [pscustomobject]@{ Content = [string]$response.Content; Headers = $response.Headers; Error = $null }
    } catch {
        return [pscustomobject]@{ Content = $null; Headers = $null; Error = $_.Exception.Message }
    }
}

function Get-ResponseJson([string]$Url) {
    $response = Get-ResponseText $Url
    if ($response.Error) { return [pscustomobject]@{ Value = $null; Headers = $response.Headers; Error = $response.Error } }
    try {
        return [pscustomobject]@{ Value = ($response.Content | ConvertFrom-Json); Headers = $response.Headers; Error = $null }
    } catch {
        return [pscustomobject]@{ Value = $null; Headers = $response.Headers; Error = $_.Exception.Message }
    }
}

function Get-ManagedRuntimeEvidence($Config, [string]$Name, [int]$Port) {
    $recordPath = Get-ServiceRecordPath $Config $Name
    $recordCheck = Test-RecordedProcess $Config $Name
    $record = if ($recordCheck) { $recordCheck.Record } else { $null }
    $workingDirectory = if ($record -and $record.PSObject.Properties.Name -contains 'workingDirectory') { [string]$record.workingDirectory } else { $null }
    $owners = @(Get-PortOwner $Port)
    return [pscustomobject]@{
        Port = $Port
        ListenerPids = @($owners | ForEach-Object { [int]$_ })
        RecordPath = $recordPath
        RecordPresent = [bool]$record
        RecordValid = [bool]($recordCheck -and $recordCheck.Valid)
        RecordReason = if ($recordCheck) { [string]$recordCheck.Reason } else { 'managed runtime record is missing' }
        WorkingDirectory = $workingDirectory
        Git = Get-RuntimeGitIdentity $workingDirectory
    }
}

function Test-WebRuntimeIdentity($Evidence, [string]$BaseUrl) {
    $entryResponse = Get-ResponseText $BaseUrl
    $identityResponse = Get-ResponseJson (([uri]$BaseUrl).GetLeftPart([System.UriPartial]::Authority) + '/__runtime-identity.json')
    $identity = $identityResponse.Value
    $errors = [Collections.Generic.List[string]]::new()
    if ($entryResponse.Error) {
        $errors.Add("browser entry is unavailable: $($entryResponse.Error)")
    } elseif ($entryResponse.Content -notmatch 'id=["'']app["'']') {
        $errors.Add('browser entry does not expose the application mount point')
    }
    if ($null -eq $identity) {
        $errors.Add("runtime identity endpoint is unavailable: $($identityResponse.Error)")
    } else {
        if ([int]$identity.schemaVersion -ne 1) { $errors.Add('schemaVersion is not 1') }
        if ([string]::IsNullOrWhiteSpace([string]$identity.productName)) { $errors.Add('product name is missing') }
        if ([string]::IsNullOrWhiteSpace([string]$identity.version)) { $errors.Add('version is missing') }
        if ([string]::IsNullOrWhiteSpace([string]$identity.gitShortSha)) { $errors.Add('Git short SHA is missing') }
        if ([string]::IsNullOrWhiteSpace([string]$identity.runMode)) { $errors.Add('run mode is missing') }
        if ([string]$identity.apiMode -notin @('SAME_ORIGIN_PROXY', 'DIRECT', 'HYBRID')) { $errors.Add('API mode is invalid') }
        $cacheControl = if ($identityResponse.Headers) { [string]$identityResponse.Headers['Cache-Control'] } else { '' }
        if ($cacheControl -notmatch '(?i)no-store') { $errors.Add('runtime identity endpoint must be served with Cache-Control: no-store') }
        if ($Evidence.Git.GitShortSha -and [string]$identity.gitShortSha -ne [string]$Evidence.Git.GitShortSha) { $errors.Add('page Git SHA does not match the runtime directory') }
        if ([string]$identity.sourceState -ne [string]$Evidence.Git.SourceState) { $errors.Add('page source state does not match the runtime directory') }
        $expectedVersion = Get-PackageVersion $Evidence.WorkingDirectory
        if ($expectedVersion -and [string]$identity.version -ne $expectedVersion) { $errors.Add('page version does not match the runtime package.json') }
        if ([string]$identity.runMode -eq 'LAN' -and [string]$identity.apiMode -ne 'SAME_ORIGIN_PROXY') { $errors.Add('LAN mode requires SAME_ORIGIN_PROXY') }
    }
    return [pscustomobject]@{ Identity = $identity; Error = $identityResponse.Error; Errors = @($errors) }
}

$config = Get-LocalConfig $ConfigPath
if ($LanMode) {
    $config = Resolve-LanRuntimeConfig $config
}
if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $config.RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot)
}
if (-not [string]::IsNullOrWhiteSpace($RuntimeDirectory)) {
    $config.RuntimeDirectory = [IO.Path]::GetFullPath($RuntimeDirectory)
}
if ($RagPort -gt 0) { $config.RagPort = $RagPort }
if ($CustomerWebPort -gt 0) { $config.CustomerWebPort = $CustomerWebPort }
if ($AdminWebPort -gt 0) { $config.AdminWebPort = $AdminWebPort }
if (-not [string]::IsNullOrWhiteSpace($CustomerWebUrl)) { $config.CustomerWebUrl = $CustomerWebUrl }
if (-not [string]::IsNullOrWhiteSpace($AdminWebUrl)) { $config.AdminWebUrl = $AdminWebUrl }

$serviceDefinitions = @(
    [pscustomobject]@{ Line = 'B'; Name = 'customer-web'; Port = [int]$config.CustomerWebPort; Url = [string]$config.CustomerWebUrl; Kind = 'web' },
    [pscustomobject]@{ Line = 'C'; Name = 'admin-web'; Port = [int]$config.AdminWebPort; Url = [string]$config.AdminWebUrl; Kind = 'web' },
    [pscustomobject]@{ Line = 'A'; Name = 'rag'; Port = [int]$config.RagPort; Url = (Get-ServiceUrl $config $config.RagPort '/api/health'); Kind = 'api' }
)

$results = foreach ($service in $serviceDefinitions) {
    $evidence = Get-ManagedRuntimeEvidence $config $service.Name $service.Port
    $errors = [Collections.Generic.List[string]]::new()
    if ($Action -ne 'Preflight' -and $evidence.ListenerPids.Count -eq 0) { $errors.Add('port is not listening') }
    if ($evidence.ListenerPids.Count -gt 1) { $errors.Add('port has multiple listening PIDs') }
    if ($evidence.ListenerPids.Count -gt 0 -and -not $evidence.RecordPresent) { $errors.Add('listener has no managed runtime record') }
    if ($evidence.RecordPresent -and -not $evidence.RecordValid) { $errors.Add("managed runtime record is invalid: $($evidence.RecordReason)") }
    if ($evidence.RecordPresent -and [string]::IsNullOrWhiteSpace($evidence.WorkingDirectory)) { $errors.Add('managed runtime record has no working directory') }
    if ($evidence.RecordPresent -and -not $evidence.Git.GitShortSha) { $errors.Add('runtime directory has no resolvable Git SHA') }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedGitShortSha) -and $evidence.Git.GitShortSha -and $evidence.Git.GitShortSha -ne $ExpectedGitShortSha) {
        $errors.Add("runtime Git SHA $($evidence.Git.GitShortSha) does not match expected $ExpectedGitShortSha")
    }

    $identity = $null
    $endpointError = $null
    if ($Action -eq 'Verify' -or $Action -eq 'Snapshot') {
        if ($service.Kind -eq 'web') {
            $webCheck = Test-WebRuntimeIdentity $evidence $service.Url
            $identity = $webCheck.Identity
            $endpointError = $webCheck.Error
            foreach ($identityError in $webCheck.Errors) { $errors.Add($identityError) }
        } else {
            $health = Get-ResponseJson $service.Url
            $openApi = Get-ResponseJson (([uri]$service.Url).GetLeftPart([System.UriPartial]::Authority) + '/openapi.json')
            $identity = [pscustomobject]@{
                productName = if ($openApi.Value) { [string]$openApi.Value.info.title } else { $null }
                version = if ($openApi.Value) { [string]$openApi.Value.info.version } else { $null }
                gitShortSha = $evidence.Git.GitShortSha
                sourceState = $evidence.Git.SourceState
                runMode = 'API_ENTRY'
                apiMode = 'DIRECT'
            }
            $endpointError = if ($health.Error) { $health.Error } else { $openApi.Error }
            if ($health.Error) { $errors.Add("A health check failed: $($health.Error)") }
            if ($openApi.Error) { $errors.Add("A OpenAPI version check failed: $($openApi.Error)") }
            if ($openApi.Value -and [string]::IsNullOrWhiteSpace([string]$openApi.Value.info.title)) { $errors.Add('A OpenAPI product name is missing') }
            if ($openApi.Value -and [string]::IsNullOrWhiteSpace([string]$openApi.Value.info.version)) { $errors.Add('A OpenAPI version is missing') }
        }
    }
    [pscustomobject]@{
        line = $service.Line
        service = $service.Name
        port = $service.Port
        listener_pids = $evidence.ListenerPids
        working_directory = $evidence.WorkingDirectory
        git_short_sha = $evidence.Git.GitShortSha
        source_state = $evidence.Git.SourceState
        managed_record = $evidence.RecordPresent
        managed_record_valid = $evidence.RecordValid
        identity = $identity
        endpoint_error = $endpointError
        result = if ($errors.Count -eq 0) { 'PASS' } else { 'FAIL' }
        errors = @($errors)
    }
}

if ($Json) {
    [pscustomobject]@{ action = $Action; generated_utc = [DateTime]::UtcNow.ToString('o'); services = @($results) } | ConvertTo-Json -Depth 8
} else {
    $results | Select-Object line, service, port, listener_pids, working_directory, git_short_sha, source_state, result | Format-Table -AutoSize
    foreach ($item in $results | Where-Object { $_.errors.Count -gt 0 }) {
        Write-Host "$($item.line) $($item.service): $($item.errors -join '; ')" -ForegroundColor Yellow
    }
}

if ($Action -in @('Preflight', 'Verify') -and @($results | Where-Object { $_.result -ne 'PASS' }).Count -gt 0) { exit 1 }
