[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Delivery.Common.ps1")
if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($RepositoryRoot)
$dirty = git -C $root status --porcelain
Assert-ExitCode "Git status"
if ($dirty) { throw "Local publishing requires a clean Git worktree so delivery matches the tested commit." }

$stage = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-publish-" + [guid]::NewGuid().ToString("N"))
$candidate = Join-Path $root (".dist.new-" + [guid]::NewGuid().ToString("N"))
$destination = Join-Path $root "dist"
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $resultPath = & (Join-Path $root "scripts\Build-Portable.ps1") `
        -RepositoryRoot $root -OutputRoot (Join-Path $stage "build") `
        -NodeExecutable $NodeExecutable -FfmpegBinDirectory $FfmpegBinDirectory `
        -SkipFrontendInstall:$SkipFrontendInstall
    $result = Get-Content -Raw -LiteralPath ($resultPath | Select-Object -Last 1) -Encoding UTF8 | ConvertFrom-Json
    New-Item -ItemType Directory -Path $candidate | Out-Null
    $archive = Join-Path $candidate "ChatWechat.zip"
    Copy-Item -LiteralPath ([string]$result.archive) -Destination $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$result.sha256) { throw "Delivery archive copy did not match the tested archive." }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($archive, $candidate)
    Assert-PackageManifest (Join-Path $candidate "ChatWechat")
    Publish-DeliveryDirectory $candidate $destination {
        param($publishedRoot)
        # Verify the actual final path, not just build staging. Failure restores both old artifacts.
        Invoke-PortableSelfTest (Join-Path $publishedRoot "ChatWechat") (Join-Path $stage "final-verification") | Out-Null
    }
    [pscustomobject]@{
        version = [string]$result.version
        commit = [string]$result.commit
        archive = Join-Path $destination "ChatWechat.zip"
        sha256 = [string]$result.sha256
        application = Join-Path $destination "ChatWechat\ChatWechat.exe"
    }
}
finally {
    Remove-BuildDirectory $root $candidate
    Remove-BuildDirectory ([IO.Path]::GetTempPath()) $stage
}
