[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SourceZip,
    [string]$PortableDirectory,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
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
    try {
        if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $backup }
        Move-Item -LiteralPath $candidate -Destination $Destination
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
    catch {
        if (-not (Test-Path -LiteralPath $Destination) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $Destination
        }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Force }
    }
}

function Publish-CoreOutputsAtomically(
    [string]$StagedFile,
    [string]$FileDestination,
    [string]$StagedDirectory,
    [string]$DirectoryDestination
) {
    $fileParent = Split-Path -Parent $FileDestination
    $directoryParent = Split-Path -Parent $DirectoryDestination
    New-Item -ItemType Directory -Force -Path $fileParent, $directoryParent | Out-Null
    $token = [guid]::NewGuid().ToString("N")
    $fileCandidate = Join-Path $fileParent ("." + [IO.Path]::GetFileName($FileDestination) + ".new-$token")
    $fileBackup = Join-Path $fileParent ("." + [IO.Path]::GetFileName($FileDestination) + ".backup-$token")
    $directoryName = [IO.Path]::GetFileName($DirectoryDestination)
    $directoryCandidate = Join-Path $directoryParent (".$directoryName.new-$token")
    $directoryBackup = Join-Path $directoryParent (".$directoryName.backup-$token")
    Assert-ChildPath $fileParent $fileCandidate
    Assert-ChildPath $fileParent $fileBackup
    Assert-ChildPath $directoryParent $directoryCandidate
    Assert-ChildPath $directoryParent $directoryBackup
    Copy-Item -LiteralPath $StagedFile -Destination $fileCandidate
    Copy-Item -LiteralPath $StagedDirectory -Destination $directoryCandidate -Recurse
    $fileBackedUp = $false
    $directoryBackedUp = $false
    $filePublished = $false
    $directoryPublished = $false
    try {
        if (Test-Path -LiteralPath $FileDestination) {
            Move-Item -LiteralPath $FileDestination -Destination $fileBackup
            $fileBackedUp = $true
        }
        if (Test-Path -LiteralPath $DirectoryDestination) {
            Move-Item -LiteralPath $DirectoryDestination -Destination $directoryBackup
            $directoryBackedUp = $true
        }
        Move-Item -LiteralPath $fileCandidate -Destination $FileDestination
        $filePublished = $true
        Move-Item -LiteralPath $directoryCandidate -Destination $DirectoryDestination
        $directoryPublished = $true
        if (Test-Path -LiteralPath $fileBackup) { Remove-Item -LiteralPath $fileBackup -Force }
        if (Test-Path -LiteralPath $directoryBackup) { Remove-Item -LiteralPath $directoryBackup -Recurse -Force }
    }
    catch {
        if ($filePublished -and (Test-Path -LiteralPath $FileDestination)) { Remove-Item -LiteralPath $FileDestination -Force }
        if ($directoryPublished -and (Test-Path -LiteralPath $DirectoryDestination)) { Remove-Item -LiteralPath $DirectoryDestination -Recurse -Force }
        if ($fileBackedUp -and (Test-Path -LiteralPath $fileBackup)) { Move-Item -LiteralPath $fileBackup -Destination $FileDestination }
        if ($directoryBackedUp -and (Test-Path -LiteralPath $directoryBackup)) { Move-Item -LiteralPath $directoryBackup -Destination $DirectoryDestination }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $fileCandidate) { Remove-Item -LiteralPath $fileCandidate -Force }
        if (Test-Path -LiteralPath $directoryCandidate) { Remove-Item -LiteralPath $directoryCandidate -Recurse -Force }
    }
}

$root = [IO.Path]::GetFullPath($RepositoryRoot)
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $SourceZip) { $SourceZip = Join-Path $desktop "发布版本\ChatWechat-source.zip" }
if (-not $PortableDirectory) { $PortableDirectory = Join-Path $desktop "免安装便携版\ChatWechat" }
$SourceZip = [IO.Path]::GetFullPath($SourceZip)
$PortableDirectory = [IO.Path]::GetFullPath($PortableDirectory)

$dirty = git -C $root status --porcelain
Assert-ExitCode "Git status"
if ($dirty) {
    throw "Local publishing requires a clean Git worktree so the source ZIP matches the tested commit."
}

$stage = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-publish-" + [guid]::NewGuid().ToString("N"))
$buildStage = Join-Path $stage "build"
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $buildResultPath = & (Join-Path $root "scripts\Build-Portable.ps1") -RepositoryRoot $root -OutputRoot $buildStage -NodeExecutable $NodeExecutable -FfmpegBinDirectory $FfmpegBinDirectory -SkipFrontendInstall:$SkipFrontendInstall
    $buildResult = Get-Content -Raw -LiteralPath ($buildResultPath | Select-Object -Last 1) | ConvertFrom-Json

    $sourceStage = Join-Path $stage "ChatWechat-source.zip"
    git -C $root archive --format=zip --output=$sourceStage HEAD
    Assert-ExitCode "Source archive"
    Publish-CoreOutputsAtomically $sourceStage $SourceZip ([string]$buildResult.portable_root) $PortableDirectory

    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourceZip).Hash.ToLowerInvariant()
    $exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PortableDirectory "ChatWechat.exe")).Hash.ToLowerInvariant()
    $hashFile = Join-Path (Split-Path -Parent $SourceZip) "SHA256SUMS.txt"
    $hashContent = @(
        "$sourceHash  ChatWechat-source.zip",
        "$exeHash  ChatWechat/ChatWechat.exe"
    ) -join "`n"
    $hashStage = Join-Path $stage "SHA256SUMS.txt"
    Set-Content -LiteralPath $hashStage -Value $hashContent -Encoding UTF8
    Replace-FileAtomically $hashStage $hashFile

    $legacyBuildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
    $legacyPortableCache = [IO.Path]::GetFullPath((Join-Path $legacyBuildRoot "portable"))
    Assert-ChildPath $legacyBuildRoot $legacyPortableCache
    if (Test-Path -LiteralPath $legacyPortableCache) {
        Remove-Item -LiteralPath $legacyPortableCache -Recurse -Force
    }

    [pscustomobject]@{
        version = $buildResult.version
        source_zip = $SourceZip
        portable_directory = $PortableDirectory
        executable = (Join-Path $PortableDirectory "ChatWechat.exe")
        hashes = $hashFile
    }
}
finally {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    Assert-ChildPath $tempRoot $stage
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
