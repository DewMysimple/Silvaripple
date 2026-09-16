[CmdletBinding()]
param(
    [string]$RepositoryRoot,
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

function Assert-LockedFile([string]$Path, [object]$Expected) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Name -cne [string]$Expected.name -or $item.Length -ne [int64]$Expected.size) {
        throw "Runtime file does not match the lock: $($item.Name)."
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
    if ($actual -cne [string]$Expected.sha256) { throw "Runtime SHA-256 mismatch: $($item.Name)." }
}

function Invoke-BackendSelfTest([string]$Executable, [string]$Output, [string]$LocalAppData, [string]$ResourceDir) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $escapedOutput = $Output.Replace('"', '\"')
    $info.Arguments = "--self-test --json --output `"$escapedOutput`""
    $info.Environment["LOCALAPPDATA"] = $LocalAppData
    $info.Environment["CHATWECHAT_RESOURCE_DIR"] = $ResourceDir
    $info.Environment["PATH"] = "$env:SystemRoot\System32;$env:SystemRoot"
    $process = [Diagnostics.Process]::Start($info)
    $process.WaitForExit()
    return $process.ExitCode
}

if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root "frontend\src-tauri\tauri.conf.json") -PathType Leaf)) {
    throw "RepositoryRoot is not a Tauri ChatWechat source tree: $root"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-tauri-" + [guid]::NewGuid().ToString("N"))
}
$stage = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $stage) { throw "Build staging path already exists: $stage" }
New-Item -ItemType Directory -Path $stage | Out-Null

if (-not $SkipQualityGate) {
    & (Join-Path $root "scripts\Invoke-QualityGate.ps1") -RepositoryRoot $root -SkipFrontendInstall:$SkipFrontendInstall
}

$lock = Get-Content -Raw -LiteralPath (Join-Path $root "packaging\runtime.lock.json") | ConvertFrom-Json
if (-not $NodeExecutable) { $NodeExecutable = (Get-Command node.exe -ErrorAction Stop).Source }
$NodeExecutable = [IO.Path]::GetFullPath($NodeExecutable)
if ((& $NodeExecutable --version).Trim() -ne "v$($lock.node.version)") { throw "Node version does not match runtime.lock.json." }
Assert-LockedFile $NodeExecutable $lock.node.files[0]

if (-not $FfmpegBinDirectory) { $FfmpegBinDirectory = Split-Path -Parent (Get-Command ffmpeg.exe -ErrorAction Stop).Source }
$FfmpegBinDirectory = [IO.Path]::GetFullPath($FfmpegBinDirectory)
$ffmpegExecutable = Join-Path $FfmpegBinDirectory "ffmpeg.exe"
$ffmpegVersion = (& $ffmpegExecutable -version 2>&1 | Select-Object -First 1).ToString()
if (-not $ffmpegVersion.StartsWith([string]$lock.ffmpeg.version_prefix, [StringComparison]::Ordinal)) { throw "FFmpeg version does not match runtime.lock.json." }
foreach ($expected in $lock.ffmpeg.files) { Assert-LockedFile (Join-Path $FfmpegBinDirectory ([string]$expected.name)) $expected }
$ffmpegLicense = Join-Path (Split-Path -Parent $FfmpegBinDirectory) ([string]$lock.ffmpeg.license.name)
Assert-LockedFile $ffmpegLicense $lock.ffmpeg.license

$resourceRoot = [IO.Path]::GetFullPath((Join-Path $root "frontend\src-tauri\resources"))
$runtimeRoot = Join-Path $resourceRoot "runtime"
if (Test-Path -LiteralPath $runtimeRoot) { Remove-Item -LiteralPath $runtimeRoot -Recurse -Force }
$nodeTarget = Join-Path $runtimeRoot "node"
$ffmpegTarget = Join-Path $runtimeRoot "ffmpeg"
New-Item -ItemType Directory -Path $nodeTarget, $ffmpegTarget | Out-Null
Copy-Item -LiteralPath $NodeExecutable -Destination (Join-Path $nodeTarget "node.exe")
Copy-Item -LiteralPath (Join-Path $root "packaging\NODE-LICENSE.txt") -Destination (Join-Path $nodeTarget "LICENSE.txt")
foreach ($expected in $lock.ffmpeg.files) { Copy-Item -LiteralPath (Join-Path $FfmpegBinDirectory ([string]$expected.name)) -Destination $ffmpegTarget }
Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $ffmpegTarget "LICENSE.txt")

$sidecar = (& (Join-Path $root "scripts\Build-TauriSidecar.ps1") -RepositoryRoot $root | Select-Object -Last 1)
$isolatedLocalAppData = Join-Path $stage "isolated-localappdata"
New-Item -ItemType Directory -Path $isolatedLocalAppData | Out-Null
$selfTestPath = Join-Path $stage "backend-self-test.json"
$selfTestExit = Invoke-BackendSelfTest $sidecar $selfTestPath $isolatedLocalAppData $resourceRoot
if ($selfTestExit -ne 0) { throw "Packaged backend self-test failed with exit code $selfTestExit." }
$selfTest = Get-Content -Raw -LiteralPath $selfTestPath | ConvertFrom-Json
if (-not $selfTest.ok -or -not $selfTest.frozen) { throw "Packaged backend did not pass frozen-mode self-test." }

Push-Location (Join-Path $root "frontend")
try {
    corepack pnpm@10.34.5 desktop:build
    Assert-ExitCode "Tauri NSIS build"
}
finally { Pop-Location }

$bundleRoot = Join-Path $root "frontend\src-tauri\target\release\bundle\nsis"
$builtInstaller = Get-ChildItem -LiteralPath $bundleRoot -Filter "*setup.exe" -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $builtInstaller) { throw "Tauri did not produce an NSIS installer." }
$installer = Join-Path $stage "ChatWechat-Setup.exe"
Copy-Item -LiteralPath $builtInstaller.FullName -Destination $installer
$version = (Get-Content -Raw -LiteralPath (Join-Path $root "pyproject.toml") | python -c "import sys,tomllib; print(tomllib.loads(sys.stdin.read())['project']['version'])").Trim()

$isolatedInstall = Join-Path $stage "isolated-install"
$installProcess = Start-Process -FilePath $installer -ArgumentList @("/S", "/D=$isolatedInstall") -Wait -PassThru -WindowStyle Hidden
if ($installProcess.ExitCode -ne 0) { throw "Tauri installer test failed with exit code $($installProcess.ExitCode)." }
$installedApp = Join-Path $isolatedInstall "ChatWechat.exe"
$installedBackend = Join-Path $isolatedInstall "chatwechat-backend.exe"
if (-not (Test-Path -LiteralPath $installedApp -PathType Leaf)) { throw "Installed Tauri application is missing ChatWechat.exe." }
if (-not (Test-Path -LiteralPath $installedBackend -PathType Leaf)) { throw "Installed Tauri application is missing its backend sidecar." }
$installedSelfTestPath = Join-Path $stage "installed-backend-self-test.json"
$installedSelfTestExit = Invoke-BackendSelfTest $installedBackend $installedSelfTestPath $isolatedLocalAppData $isolatedInstall
if ($installedSelfTestExit -ne 0) { throw "Installed backend self-test failed with exit code $installedSelfTestExit." }
$installedSelfTest = Get-Content -Raw -LiteralPath $installedSelfTestPath | ConvertFrom-Json
if (-not $installedSelfTest.ok -or -not $installedSelfTest.runtime_tools.node.bundled -or -not $installedSelfTest.runtime_tools.ffmpeg.bundled) {
    throw "Installed backend did not use the bundled runtime tools."
}
$uninstaller = Join-Path $isolatedInstall "uninstall.exe"
if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw "Tauri uninstaller is missing." }
$uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @("/S") -Wait -PassThru -WindowStyle Hidden
if ($uninstallProcess.ExitCode -ne 0 -or (Test-Path -LiteralPath $installedApp)) { throw "Tauri uninstall verification failed." }

$result = [ordered]@{
    version = $version
    staging_root = $stage
    installer = $installer
    test_installer = $installer
    sidecar = $sidecar
    self_test = $selfTestPath
    installer_self_test = $installedSelfTestPath
    bundle_root = $bundleRoot
}
$resultPath = Join-Path $stage "installer-result.json"
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
