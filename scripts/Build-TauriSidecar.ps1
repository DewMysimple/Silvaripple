[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$OutputFile
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root "pyproject.toml") -PathType Leaf)) {
    throw "RepositoryRoot is not a ChatWechat source tree: $root"
}
$hostLine = rustc -vV | Where-Object { $_ -like "host:*" } | Select-Object -First 1
if (-not $hostLine) { throw "rustc did not report a host target." }
$target = ($hostLine -split ":", 2)[1].Trim()
$binaryName = "chatwechat-backend-$target.exe"
if (-not $OutputFile) {
    $OutputFile = Join-Path $root "frontend\src-tauri\binaries\$binaryName"
}
$output = [IO.Path]::GetFullPath($OutputFile)
$expectedParent = [IO.Path]::GetFullPath((Join-Path $root "frontend\src-tauri\binaries")).TrimEnd('\') + '\'
if (-not $output.StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Sidecar output must stay in frontend/src-tauri/binaries: $output"
}

$stage = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-sidecar-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $dist = Join-Path $stage "dist"
    $work = Join-Path $stage "work"
    $env:CHATWECHAT_BACKEND_NAME = "chatwechat-backend"
    Push-Location $root
    try {
        python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $root "packaging\ChatWechat.spec")
        Assert-ExitCode "Python sidecar build"
    }
    finally {
        Remove-Item Env:CHATWECHAT_BACKEND_NAME -ErrorAction SilentlyContinue
        Pop-Location
    }
    $built = Join-Path $dist "chatwechat-backend.exe"
    if (-not (Test-Path -LiteralPath $built -PathType Leaf)) {
        throw "PyInstaller did not produce the ChatWechat backend sidecar."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output) | Out-Null
    $candidate = "$output.new"
    Copy-Item -LiteralPath $built -Destination $candidate -Force
    Move-Item -LiteralPath $candidate -Destination $output -Force
    Write-Output $output
}
finally {
    $temp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    $resolvedStage = [IO.Path]::GetFullPath($stage)
    if ($resolvedStage.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStage)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
