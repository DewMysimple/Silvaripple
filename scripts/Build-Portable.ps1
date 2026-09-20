[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$OutputRoot,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipQualityGate,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Delivery.Common.ps1")
if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($RepositoryRoot)
$tauriRoot = Join-Path $root "frontend\src-tauri"
if (-not (Test-Path -LiteralPath (Join-Path $tauriRoot "tauri.conf.json") -PathType Leaf)) { throw "RepositoryRoot is not a ChatWechat source tree: $root" }
if (-not $OutputRoot) { $OutputRoot = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-portable-" + [guid]::NewGuid().ToString("N")) }
$stage = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $stage) { throw "Build staging path already exists: $stage" }
New-Item -ItemType Directory -Path $stage | Out-Null

if (-not $SkipQualityGate) {
    & (Join-Path $root "scripts\Invoke-QualityGate.ps1") -RepositoryRoot $root -SkipFrontendInstall:$SkipFrontendInstall
}
Copy-VerifiedRuntime $root $NodeExecutable $FfmpegBinDirectory
$sidecar = (& (Join-Path $root "scripts\Build-TauriSidecar.ps1") -RepositoryRoot $root | Select-Object -Last 1)
Push-Location (Join-Path $root "frontend")
try {
    corepack pnpm@10.34.5 desktop:build
    Assert-ExitCode "Tauri portable build"
}
finally { Pop-Location }

$appRoot = Join-Path $stage "ChatWechat"
New-Item -ItemType Directory -Path $appRoot | Out-Null
$cargoMetadata = cargo metadata --no-deps --format-version 1 --manifest-path (Join-Path $tauriRoot "Cargo.toml") | ConvertFrom-Json
Assert-ExitCode "Cargo target directory resolution"
$builtApp = Join-Path ([string]$cargoMetadata.target_directory) "release\ChatWechat.exe"
Copy-Item -LiteralPath $builtApp -Destination (Join-Path $appRoot "ChatWechat.exe")
Copy-Item -LiteralPath $sidecar -Destination (Join-Path $appRoot "chatwechat-backend.exe")

# Use the same resource mapping as the desktop host, so packaging cannot drift.
Copy-TauriResources $tauriRoot $appRoot
$licenseRoot = Join-Path $appRoot "licenses"
New-Item -ItemType Directory -Path $licenseRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $root "chatwechat\vendor\silk-wasm\LICENSE") -Destination (Join-Path $licenseRoot "silk-wasm-LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $root "packaging\PORTABLE-README.txt") -Destination (Join-Path $appRoot "README.txt")
$version = (Get-Content -Raw -LiteralPath (Join-Path $root "pyproject.toml") | python -c "import sys,tomllib; print(tomllib.loads(sys.stdin.read())['project']['version'])").Trim()
Assert-ExitCode "Project version resolution"
$commit = (git -C $root rev-parse HEAD).Trim()
Assert-ExitCode "Build commit resolution"
Write-PackageManifest $appRoot $version $commit

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = Join-Path $stage "ChatWechat.zip"
[IO.Compression.ZipFile]::CreateFromDirectory($appRoot, $archive, [IO.Compression.CompressionLevel]::Optimal, $true)
$expandedRoot = Join-Path $stage "expanded"
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $expandedRoot)
$expandedApp = Join-Path $expandedRoot "ChatWechat"
$selfTest = Invoke-PortableSelfTest $expandedApp (Join-Path $stage "verification")
$result = [ordered]@{
    version = $version
    commit = $commit
    staging_root = $stage
    archive = $archive
    sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    application_root = $expandedApp
    self_test = $selfTest
}
$resultPath = Join-Path $stage "portable-result.json"
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
