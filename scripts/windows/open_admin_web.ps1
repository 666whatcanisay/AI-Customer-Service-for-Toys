[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common_ai_customer_service.ps1')

try {
    $config = Get-LocalConfig $ConfigPath
    $url = Open-AdminWeb $config -NoLaunch:$NoLaunch
    if ($NoLaunch) {
        Write-Host "管理后台可用：$url" -ForegroundColor Green
    } else {
        Write-Host "已在服务器本机默认浏览器中打开管理后台：$url" -ForegroundColor Green
    }
    Write-Output $url
} catch {
    Write-Error $_
    exit 1
}
