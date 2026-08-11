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

foreach ($required in @('ChannelAgent.exe', 'app\channel-agent.pyz', 'release-manifest.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $required) -PathType Leaf)) {
        throw "Required package file is missing: $required"
    }
}
if ($InstallRoot -eq $PackageRoot) { throw 'InstallRoot cannot equal PackageRoot.' }
$packageManifest = Get-Content -LiteralPath (Join-Path $PackageRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
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

    # Stop the previous runtime before replacing files. This preserves the data
    # directory and lets a novice safely run the same installer for upgrades.
    $existingExecutable = Join-Path $InstallRoot 'ChannelAgent.exe'
    if (Test-Path -LiteralPath $existingExecutable -PathType Leaf) {
        $escapedDataRoot = $DataRoot.Replace('"', '\"')
        $stopProcess = Start-Process -FilePath $existingExecutable `
            -ArgumentList "stop --data-root `"$escapedDataRoot`" --wait-seconds 12" `
            -WindowStyle Hidden -Wait -PassThru
        if ($stopProcess.ExitCode -ne 0 -and -not $Force) {
            throw 'The existing Channel Agent could not be stopped safely.'
        }
    }

    # A tray process does not own business state. Terminate only launchers whose
    # executable path is exactly the known install/package launcher, so no
    # unrelated ChannelAgent process can be affected.
    $knownLaunchers = @(
        [System.IO.Path]::GetFullPath((Join-Path $InstallRoot 'ChannelAgent.exe')),
        [System.IO.Path]::GetFullPath((Join-Path $PackageRoot 'ChannelAgent.exe'))
    )
    Get-CimInstance Win32_Process -Filter "Name='ChannelAgent.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.ExecutablePath -and $knownLaunchers -contains [System.IO.Path]::GetFullPath($_.ExecutablePath)) {
            Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        }
    }
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
Get-ChildItem -LiteralPath $PackageRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $InstallRoot -Recurse -Force
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
