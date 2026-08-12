[CmdletBinding()]
param(
    [string]$PackageRoot,
    [string]$InstallRoot,
    [string]$DataRoot,
    [string]$StartupDirectory,
    [switch]$EnableAutoStart,
    [switch]$CreateShortcuts,
    [switch]$Launch,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if (-not $PackageRoot) { $PackageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')) }
$PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\AI-CS\ChannelAgent' }
if (-not $DataRoot) { $DataRoot = Join-Path $env:LOCALAPPDATA 'AI-CS\ChannelAgent' }
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
. (Join-Path $PSScriptRoot 'ChannelAgentShortcutName.ps1')

function Set-PrivateRuntimeDirectoryAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $administrators = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $inheritance = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    $propagation = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $acl = [System.Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($identity in @($currentUser, $system, $administrators)) {
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $identity,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            $propagation,
            $allow
        )
        [void]$acl.AddAccessRule($rule)
    }
    [System.IO.Directory]::SetAccessControl($Path, $acl)
}

function Assert-PackageIntegrity([string]$Root, $Manifest) {
    foreach ($required in @('ChannelAgent.exe', 'app\channel-agent.pyz', 'release-manifest.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $required) -PathType Leaf)) {
            throw "Required package file is missing: $required"
        }
    }
    if ($Manifest.PSObject.Properties.Name -contains 'files') {
        foreach ($file in @($Manifest.files)) {
            $candidate = Join-Path $Root ([string]$file.path).Replace('/', '\')
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                throw "Manifest file is missing: $($file.path)"
            }
            $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne ([string]$file.sha256).ToLowerInvariant()) {
                throw "Manifest file hash mismatch: $($file.path)"
            }
        }
    }
}

function Get-InstallOwnedProcesses([string]$InstallDirectory) {
    $prefix = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\') + '\'
    @(Get-Process ChannelAgent,python,pythonw -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and [IO.Path]::GetFullPath($_.Path).StartsWith(
                $prefix,
                [StringComparison]::OrdinalIgnoreCase
            )
        } catch { $false }
    })
}

function Stop-KnownAgentLauncher([string]$InstallDirectory, [string]$AgentDataRoot) {
    $Executable = Join-Path $InstallDirectory 'ChannelAgent.exe'
    if (Test-Path -LiteralPath $Executable -PathType Leaf) {
        $escapedDataRoot = $AgentDataRoot.Replace('"', '\"')
        $stopProcess = Start-Process -FilePath $Executable `
            -ArgumentList "stop --data-root `"$escapedDataRoot`" --wait-seconds 12" `
            -WindowStyle Hidden -Wait -PassThru
        if ($stopProcess.ExitCode -ne 0 -and -not $Force) {
            throw 'The existing Channel Agent could not be stopped safely.'
        }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $matching = @(Get-InstallOwnedProcesses $InstallDirectory)
        if ($matching.Count -eq 0) { return }
        if ($Force) {
            $matching | Stop-Process -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'The existing Channel Agent still owns the install directory.'
}

if ($InstallRoot -eq $PackageRoot) { throw 'InstallRoot cannot equal PackageRoot.' }
$packageManifest = Get-Content -LiteralPath (Join-Path $PackageRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-PackageIntegrity $PackageRoot $packageManifest
$existingInstall = Test-Path -LiteralPath $InstallRoot -PathType Container
if ($existingInstall) {
    $existingManifestPath = Join-Path $InstallRoot 'release-manifest.json'
    if ((Test-Path -LiteralPath $existingManifestPath -PathType Leaf) -and -not $Force) {
        $existingManifest = Get-Content -LiteralPath $existingManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        try {
            if ([version]$existingManifest.version -gt [version]$packageManifest.version) {
                throw "Installed version $($existingManifest.version) is newer than package version $($packageManifest.version)."
            }
        }
        catch [System.Management.Automation.RuntimeException] { throw }
        catch { throw 'Installed or package version is invalid.' }
    }

    # Do not touch the installed tree until the new package is fully staged and
    # the exact known launcher has released its file handles.
    Stop-KnownAgentLauncher $InstallRoot $DataRoot
}

$installParent = Split-Path -Parent $InstallRoot
$installLeaf = Split-Path -Leaf $InstallRoot
New-Item -ItemType Directory -Path $installParent -Force | Out-Null
$transactionId = [Guid]::NewGuid().ToString('N')
$stageRoot = Join-Path $installParent ".$installLeaf.incoming-$transactionId"
$rollbackRoot = Join-Path $installParent ".$installLeaf.rollback-$transactionId"
try {
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $PackageRoot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stageRoot -Recurse -Force
    }
    Assert-PackageIntegrity $stageRoot $packageManifest
    if ($existingInstall) { Move-Item -LiteralPath $InstallRoot -Destination $rollbackRoot }
    try {
        Move-Item -LiteralPath $stageRoot -Destination $InstallRoot
    } catch {
        if (Test-Path -LiteralPath $rollbackRoot -PathType Container) {
            Move-Item -LiteralPath $rollbackRoot -Destination $InstallRoot
        }
        throw
    }
    if (Test-Path -LiteralPath $rollbackRoot -PathType Container) {
        Remove-Item -LiteralPath $rollbackRoot -Recurse -Force
    }
} finally {
    if (Test-Path -LiteralPath $stageRoot -PathType Container) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
foreach ($relative in @('config', 'logs', 'runtime')) {
    New-Item -ItemType Directory -Path (Join-Path $DataRoot $relative) -Force | Out-Null
}
# Binding and session state are writable only by the signed-in Windows user,
# local Administrators and SYSTEM.  Reapplying this on upgrade repairs older
# installations whose runtime directory inherited a read-only or foreign ACL.
Set-PrivateRuntimeDirectoryAcl -Path (Join-Path $DataRoot 'runtime')
$activeConfig = Join-Path $DataRoot 'config\agent.json'
# The real config is created only after LAN discovery, connection-code entry,
# certificate verification and an explicit human confirmation in the wizard.
# Never seed a deployable placeholder that could bypass first-launch onboarding.
$firstLaunchRequired = -not (Test-Path -LiteralPath $activeConfig -PathType Leaf)
[ordered]@{
    schema_version = '1.0'
    installed_version = $packageManifest.version
    install_root = $InstallRoot
    data_root = $DataRoot
    installed_at = [DateTimeOffset]::UtcNow.ToString('o')
    first_launch_required = $firstLaunchRequired
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $DataRoot 'runtime\install-state.json') -Encoding UTF8

if ($EnableAutoStart) {
    $arguments = @('autostart', 'enable', '--data-root', $DataRoot)
    if ($StartupDirectory) { $arguments += @('--startup-directory', [System.IO.Path]::GetFullPath($StartupDirectory)) }
    # WindowsApplication launchers do not reliably propagate LASTEXITCODE to
    # the calling PowerShell host. Run the packaged CLI through the embedded
    # Python runtime so installation gets the real deterministic exit code.
    & (Join-Path $InstallRoot 'runtime\python\python.exe') `
        (Join-Path $InstallRoot 'app\channel-agent.pyz') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Auto-start configuration failed.' }
}

if ($CreateShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) (Get-ChannelAgentShortcutName)
    $shortcut = $shell.CreateShortcut($desktopShortcut)
    $shortcut.TargetPath = Join-Path $InstallRoot 'ChannelAgent.exe'
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = 'AI-CS Channel Agent 客服电脑客户端'
    $shortcut.IconLocation = "$(Join-Path $InstallRoot 'ChannelAgent.exe'),0"
    $shortcut.Save()

    # Explorer can retain the previous executable icon after an in-place
    # upgrade. Refresh the per-user icon cache without restarting Explorer.
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\ie4uinit.exe') `
        -ArgumentList '-show' -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
}

if ($Launch) {
    Start-Process -FilePath (Join-Path $InstallRoot 'ChannelAgent.exe') -WindowStyle Hidden
}

Write-Output "install_root=$InstallRoot"
Write-Output "data_root=$DataRoot"
Write-Output "version=$($packageManifest.version)"
Write-Output "first_launch_required=$firstLaunchRequired"
