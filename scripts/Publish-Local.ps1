[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SourceZip,
    [string]$InstallerOutput,
    [string]$NsisCompiler,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $childFull = [IO.Path]::GetFullPath($Child)
    if (-not $childFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside the expected parent: $childFull"
    }
}

function Replace-FileAtomically([string]$StagedFile, [string]$Destination) {
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $candidate = Join-Path $parent ("." + [IO.Path]::GetFileName($Destination) + ".new-" + [guid]::NewGuid().ToString("N"))
    $backup = Join-Path $parent ("." + [IO.Path]::GetFileName($Destination) + ".backup-" + [guid]::NewGuid().ToString("N"))
    Assert-ChildPath $parent $candidate
    Assert-ChildPath $parent $backup
    Copy-Item -LiteralPath $StagedFile -Destination $candidate
    $backedUp = $false
    $published = $false
    try {
        if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $backup; $backedUp = $true }
        Move-Item -LiteralPath $candidate -Destination $Destination
        $published = $true
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
    catch {
        if ($published -and (Test-Path -LiteralPath $Destination)) { Remove-Item -LiteralPath $Destination -Force }
        if ($backedUp -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $Destination }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Force }
    }
}

$root = [IO.Path]::GetFullPath($RepositoryRoot)
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $SourceZip) { $SourceZip = Join-Path $desktop "发布版本\ChatWechat-source.zip" }
if (-not $InstallerOutput) { $InstallerOutput = Join-Path $desktop "发布版本\ChatWechat-Setup.exe" }
$SourceZip = [IO.Path]::GetFullPath($SourceZip)
$InstallerOutput = [IO.Path]::GetFullPath($InstallerOutput)

$dirty = git -C $root status --porcelain
Assert-ExitCode "Git status"
if ($dirty) { throw "Local publishing requires a clean Git worktree so the source ZIP matches the tested commit." }

$stage = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-publish-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $buildResultPath = & (Join-Path $root "scripts\Build-Installer.ps1") `
        -RepositoryRoot $root `
        -OutputRoot (Join-Path $stage "build") `
        -NsisCompiler $NsisCompiler `
        -NodeExecutable $NodeExecutable `
        -FfmpegBinDirectory $FfmpegBinDirectory `
        -SkipFrontendInstall:$SkipFrontendInstall
    $buildResult = Get-Content -Raw -LiteralPath ($buildResultPath | Select-Object -Last 1) | ConvertFrom-Json

    $sourceStage = Join-Path $stage "ChatWechat-source.zip"
    git -C $root archive --format=zip --output=$sourceStage HEAD
    Assert-ExitCode "Source archive"
    Replace-FileAtomically $sourceStage $SourceZip
    Replace-FileAtomically ([string]$buildResult.installer) $InstallerOutput

    $hashFile = Join-Path (Split-Path -Parent $SourceZip) "SHA256SUMS.txt"
    $hashStage = Join-Path $stage "SHA256SUMS.txt"
    $hashContent = @(
        "$((Get-FileHash -Algorithm SHA256 -LiteralPath $SourceZip).Hash.ToLowerInvariant())  ChatWechat-source.zip",
        "$((Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerOutput).Hash.ToLowerInvariant())  ChatWechat-Setup.exe"
    ) -join "`n"
    Set-Content -LiteralPath $hashStage -Value $hashContent -Encoding UTF8
    Replace-FileAtomically $hashStage $hashFile

    $legacyBuildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
    $legacyPortableCache = [IO.Path]::GetFullPath((Join-Path $legacyBuildRoot "portable"))
    Assert-ChildPath $legacyBuildRoot $legacyPortableCache
    if (Test-Path -LiteralPath $legacyPortableCache) { Remove-Item -LiteralPath $legacyPortableCache -Recurse -Force }

    [pscustomobject]@{
        version = [string]$buildResult.version
        source_zip = $SourceZip
        installer = $InstallerOutput
        hashes = $hashFile
        previous_portable_untouched = $true
    }
}
finally {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    Assert-ChildPath $tempRoot $stage
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
