[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$expectedName = 'AI-CS-Channel-Execution-Engine'
if ((Split-Path $repoRoot -Leaf) -ne $expectedName -or -not (Test-Path -LiteralPath (Join-Path $repoRoot 'pyproject.toml'))) {
    throw '仓库根目录校验失败，拒绝执行清理。'
}

$targets = [System.Collections.Generic.List[string]]::new()
foreach ($relative in @('.pytest_cache', 'dist\windows-client-v1\.stage')) {
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $relative))
    if (Test-Path -LiteralPath $candidate) { $targets.Add($candidate) }
}
foreach ($baseRelative in @('src', 'tests', 'scripts')) {
    $base = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $baseRelative))
    if (-not $base.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw '清理目录越过仓库边界。'
    }
    Get-ChildItem -LiteralPath $base -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object { $targets.Add($_.FullName) }
}
$runtimeRoot = Join-Path $repoRoot '.runtime'
if (Test-Path -LiteralPath $runtimeRoot -PathType Container) {
    Get-ChildItem -LiteralPath $runtimeRoot -Directory -Filter 'package-acceptance-*' |
        ForEach-Object { $targets.Add($_.FullName) }
}

$uniqueTargets = $targets | Sort-Object -Unique
if (-not $uniqueTargets) {
    Write-Host '没有发现允许清理的缓存或临时验收目录。'
    exit 0
}

foreach ($target in $uniqueTargets) {
    $resolved = [System.IO.Path]::GetFullPath($target)
    if (-not $resolved.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "目标越过仓库边界：$resolved"
    }
    $relative = $resolved.Substring($repoRoot.Length + 1)
    if (-not $Apply) {
        Write-Host "[预览] $relative"
        continue
    }
    if ($PSCmdlet.ShouldProcess($resolved, '删除可再生成的缓存/临时验收目录')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
        Write-Host "[已清理] $relative"
    }
}

if (-not $Apply) {
    Write-Host '当前仅为预览。确认后使用 -Apply；不会删除运行数据、Receipt、证据、浏览器 Profile 或未知文件。'
}
