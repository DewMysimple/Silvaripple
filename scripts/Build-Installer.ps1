[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputRoot,
    [string]$NsisCompiler,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipQualityGate,
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

function Read-InstallerLock([string]$Root) {
    return Get-Content -Raw -LiteralPath (Join-Path $Root "packaging\installer.lock.json") | ConvertFrom-Json
}

function Find-NsisCompiler([string]$Requested, [object]$Lock, [string]$Stage) {
    if ($Requested) {
        $candidate = [IO.Path]::GetFullPath($Requested)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "NSIS compiler was not found: $candidate" }
        return $candidate
    }
    $command = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\NSIS\Bin\makensis.exe",
        "$env:ProgramFiles\NSIS\Bin\makensis.exe",
        "$env:LOCALAPPDATA\Programs\NSIS\Bin\makensis.exe",
        "$env:LOCALAPPDATA\tauri\NSIS\Bin\makensis.exe"
    )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }

    $cache = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-nsis-" + [string]$Lock.nsis.version)
    $archive = Join-Path $cache ("nsis-" + [string]$Lock.nsis.version + ".zip")
    $extract = Join-Path $cache "extracted"
    $compiler = Join-Path $extract ([string]$Lock.nsis.compiler_relative_path)
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
            Write-Host "Downloading pinned NSIS $($Lock.nsis.version)..."
            Invoke-WebRequest -Uri ([string]$Lock.nsis.source) -OutFile $archive
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
        if ($hash -cne [string]$Lock.nsis.sha256) {
            throw "NSIS archive SHA-256 mismatch: $hash"
        }
        if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
        Expand-Archive -LiteralPath $archive -DestinationPath $extract
    }
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
        throw "Pinned NSIS archive does not contain $($Lock.nsis.compiler_relative_path)."
    }
    return [IO.Path]::GetFullPath($compiler)
}

function Assert-NsisVersion([string]$Compiler, [object]$Lock) {
    $reported = (& $Compiler /VERSION 2>&1 | Select-Object -Last 1).ToString().Trim()
    Assert-ExitCode "NSIS version check"
    if ($reported -cne "v$([string]$Lock.nsis.version)") {
        throw "NSIS version does not match installer.lock.json: $reported"
    }
}

function Invoke-WindowedProcess([string]$FilePath, [string[]]$Arguments, [string]$LocalAppData, [string]$PathValue) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FilePath
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    foreach ($argument in $Arguments) { [void]$info.ArgumentList.Add($argument) }
    $info.Environment["LOCALAPPDATA"] = $LocalAppData
    $info.Environment["PATH"] = $PathValue
    $process = [Diagnostics.Process]::Start($info)
    $process.WaitForExit()
    return $process.ExitCode
}

function Invoke-Nsis([string]$Compiler, [string]$Script, [string]$Version, [string]$StagingRoot, [string]$Output, [string]$IconFile, [switch]$SkipMigration, [switch]$SkipShortcuts) {
    $arguments = @(
        "/V2",
        "/DAPP_VERSION=$Version",
        "/DSTAGING_ROOT=$StagingRoot",
        "/DOUTPUT_FILE=$Output",
        "/DICON_FILE=$IconFile"
    )
    if ($SkipMigration) { $arguments += "/DSKIP_LEGACY_MIGRATION" }
    if ($SkipShortcuts) { $arguments += "/DSKIP_SHORTCUTS" }
    $arguments += $Script
    & $Compiler @arguments
    Assert-ExitCode "NSIS installer build"
    if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) { throw "NSIS did not produce an installer: $Output" }
}

$root = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root "pyproject.toml") -PathType Leaf)) {
    throw "RepositoryRoot is not a ChatWechat source tree: $root"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-installer-" + [guid]::NewGuid().ToString("N"))
}
$stage = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $stage) { throw "Build staging path already exists: $stage" }
New-Item -ItemType Directory -Path $stage | Out-Null

$lock = Read-InstallerLock $root
$buildStage = Join-Path $stage "application-build"
$buildResultPath = & (Join-Path $root "scripts\Build-AppStaging.ps1") `
    -RepositoryRoot $root `
    -OutputRoot $buildStage `
    -NodeExecutable $NodeExecutable `
    -FfmpegBinDirectory $FfmpegBinDirectory `
    -SkipQualityGate:$SkipQualityGate `
    -SkipFrontendInstall:$SkipFrontendInstall
$buildResult = Get-Content -Raw -LiteralPath ($buildResultPath | Select-Object -Last 1) | ConvertFrom-Json
$version = [string]$buildResult.version
$installer = Join-Path $stage "ChatWechat-Setup.exe"
$compiler = Find-NsisCompiler $NsisCompiler $lock $stage
Assert-NsisVersion $compiler $lock
$script = Join-Path $root "packaging\ChatWechat.nsi"
$icon = Join-Path $root "packaging\ChatWechat.ico"
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw "ChatWechat application icon is missing." }
$stagingRoot = [IO.Path]::GetFullPath([string]$buildResult.application_root)
Assert-ChildPath $stage $stagingRoot
Invoke-Nsis $compiler $script $version $stagingRoot $installer $icon

$testInstaller = Join-Path $stage "ChatWechat-Setup-test.exe"
Invoke-Nsis $compiler $script $version $stagingRoot $testInstaller $icon -SkipMigration -SkipShortcuts

$isolatedInstall = Join-Path $stage "isolated-install"
$isolatedLocalAppData = Join-Path $stage "isolated-localappdata"
New-Item -ItemType Directory -Path $isolatedLocalAppData | Out-Null
$savedLocalAppData = $env:LOCALAPPDATA
$savedPath = $env:PATH
try {
    $env:LOCALAPPDATA = $isolatedLocalAppData
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $installProcess = Start-Process -FilePath $testInstaller -ArgumentList @("/S", "/D=$isolatedInstall") -Wait -PassThru -WindowStyle Hidden
    if ($installProcess.ExitCode -ne 0) { throw "Isolated installer test failed with exit code $($installProcess.ExitCode)." }
    $installedExe = Join-Path $isolatedInstall "ChatWechat.exe"
    if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf)) { throw "Installed ChatWechat.exe is missing." }
    $selfTestPath = Join-Path $stage "installed-self-test.json"
    $selfTestExit = Invoke-WindowedProcess $installedExe @("--self-test", "--json", "--output", $selfTestPath) $isolatedLocalAppData $env:PATH
    if ($selfTestExit -ne 0) { throw "Installed application self-test failed with exit code $selfTestExit." }
    $installedSelfTest = Get-Content -Raw -LiteralPath $selfTestPath | ConvertFrom-Json
    if (-not $installedSelfTest.ok -or -not $installedSelfTest.frozen) { throw "Installed application self-test did not validate frozen mode." }
    $uninstaller = Join-Path $isolatedInstall "Uninstall.exe"
    $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @("/S") -Wait -PassThru -WindowStyle Hidden
    if ($uninstallProcess.ExitCode -ne 0) { throw "Isolated uninstall test failed with exit code $($uninstallProcess.ExitCode)." }
    if (Test-Path -LiteralPath $isolatedInstall) { throw "Isolated uninstall left the program directory behind." }
}
finally {
    $env:LOCALAPPDATA = $savedLocalAppData
    $env:PATH = $savedPath
}

$result = [ordered]@{
    version = $version
    staging_root = $stage
    application_root = $stagingRoot
    installer = $installer
    nsis_compiler = $compiler
    self_test = [string]$buildResult.self_test
    installer_self_test = (Join-Path $stage "installed-self-test.json")
}
$resultPath = Join-Path $stage "installer-result.json"
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
