[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$InstallerOutput,
    [string]$InstalledRoot,
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

function Invoke-WindowedSelfTest([string]$Executable, [string]$OutputPath) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    foreach ($argument in @("--self-test", "--json", "--output", $OutputPath)) { [void]$info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($info)
    $process.WaitForExit()
    return $process.ExitCode
}

$root = [IO.Path]::GetFullPath($RepositoryRoot)
$artifactRoot = Join-Path $root "artifacts\发布版本"
if (-not $InstalledRoot) { $InstalledRoot = Join-Path $root "artifacts\安装版\ChatWechat" }
if (-not $InstallerOutput) { $InstallerOutput = Join-Path $artifactRoot "ChatWechat-Setup.exe" }
$InstallerOutput = [IO.Path]::GetFullPath($InstallerOutput)
$InstalledRoot = [IO.Path]::GetFullPath($InstalledRoot)
$installArtifactRoot = [IO.Path]::GetFullPath((Join-Path $root "artifacts\安装版"))
Assert-ChildPath $root $artifactRoot
Assert-ChildPath $artifactRoot $InstallerOutput
Assert-ChildPath $installArtifactRoot $InstalledRoot

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

    Replace-FileAtomically ([string]$buildResult.installer) $InstallerOutput

    $hashFile = Join-Path $artifactRoot "SHA256SUMS.txt"
    $hashStage = Join-Path $stage "SHA256SUMS.txt"
    $hashContent = "$((Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerOutput).Hash.ToLowerInvariant())  ChatWechat-Setup.exe"
    Set-Content -LiteralPath $hashStage -Value $hashContent -Encoding UTF8
    Replace-FileAtomically $hashStage $hashFile

    $legacySourceZip = Join-Path $artifactRoot "ChatWechat-source.zip"
    if (Test-Path -LiteralPath $legacySourceZip -PathType Leaf) { Remove-Item -LiteralPath $legacySourceZip -Force }

    $localTestInstaller = [IO.Path]::GetFullPath([string]$buildResult.test_installer)
    $installParent = Split-Path -Parent $InstalledRoot
    New-Item -ItemType Directory -Force -Path $installParent | Out-Null
    $installBackup = Join-Path $installParent (".ChatWechat.backup-" + [guid]::NewGuid().ToString("N"))
    $installBackedUp = $false
    try {
        if (Test-Path -LiteralPath $InstalledRoot) { Move-Item -LiteralPath $InstalledRoot -Destination $installBackup; $installBackedUp = $true }
        $installProcess = Start-Process -FilePath $localTestInstaller -ArgumentList @("/S", "/D=$InstalledRoot") -Wait -PassThru -WindowStyle Hidden
        if ($installProcess.ExitCode -ne 0) { throw "工程内安装失败，退出码 $($installProcess.ExitCode)。" }
        $installedExecutable = Join-Path $InstalledRoot "ChatWechat.exe"
        if (-not (Test-Path -LiteralPath $installedExecutable -PathType Leaf)) { throw "工程内安装缺少 ChatWechat.exe。" }
        $installedSelfTest = Join-Path $stage "project-installed-self-test.json"
        $selfTestExit = Invoke-WindowedSelfTest $installedExecutable $installedSelfTest
        if ($selfTestExit -ne 0) { throw "工程内安装版自检失败，退出码 $selfTestExit。" }
        $selfTest = Get-Content -Raw -LiteralPath $installedSelfTest | ConvertFrom-Json
        if (-not $selfTest.ok -or -not $selfTest.frozen) { throw "工程内安装版未通过冻结模式自检。" }
        if ($installBackedUp -and (Test-Path -LiteralPath $installBackup)) { Remove-Item -LiteralPath $installBackup -Recurse -Force }
    }
    catch {
        if (Test-Path -LiteralPath $InstalledRoot) { Remove-Item -LiteralPath $InstalledRoot -Recurse -Force }
        if ($installBackedUp -and (Test-Path -LiteralPath $installBackup)) { Move-Item -LiteralPath $installBackup -Destination $InstalledRoot }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $installBackup) { Remove-Item -LiteralPath $installBackup -Recurse -Force }
    }

    $legacyBuildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
    $legacyPortableCache = [IO.Path]::GetFullPath((Join-Path $legacyBuildRoot "portable"))
    Assert-ChildPath $legacyBuildRoot $legacyPortableCache
    if (Test-Path -LiteralPath $legacyPortableCache) { Remove-Item -LiteralPath $legacyPortableCache -Recurse -Force }

    [pscustomobject]@{
        version = [string]$buildResult.version
        installer = $InstallerOutput
        hashes = $hashFile
        installed_root = $InstalledRoot
        artifact_root = (Split-Path -Parent $InstallerOutput)
    }
}
finally {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    Assert-ChildPath $tempRoot $stage
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
