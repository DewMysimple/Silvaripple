[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputRoot,
    [string]$NodeExecutable,
    [string]$FfmpegBinDirectory,
    [switch]$SkipQualityGate,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

function Assert-LockedFile([string]$Path, [object]$Expected) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Name -cne [string]$Expected.name) {
        throw "Runtime file name mismatch: $($item.Name)."
    }
    if ($item.Length -ne [int64]$Expected.size) {
        throw "Runtime file size mismatch: $($item.Name)."
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
    if ($actual -cne [string]$Expected.sha256) {
        throw "Runtime SHA-256 mismatch: $($item.Name)."
    }
}

$root = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root "pyproject.toml") -PathType Leaf)) {
    throw "RepositoryRoot is not a ChatWechat source tree: $root"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path ([IO.Path]::GetTempPath()) ("ChatWechat-build-" + [guid]::NewGuid().ToString("N"))
}
$stage = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $stage) {
    throw "Build staging path already exists: $stage"
}
New-Item -ItemType Directory -Path $stage | Out-Null

if (-not $SkipQualityGate) {
    & (Join-Path $root "scripts\Invoke-QualityGate.ps1") -RepositoryRoot $root -SkipFrontendInstall:$SkipFrontendInstall
}

$lock = Get-Content -Raw -LiteralPath (Join-Path $root "packaging\runtime.lock.json") | ConvertFrom-Json
if (-not $NodeExecutable) {
    $NodeExecutable = (Get-Command node.exe -ErrorAction Stop).Source
}
$NodeExecutable = [IO.Path]::GetFullPath($NodeExecutable)
if ((& $NodeExecutable --version).Trim() -ne "v$($lock.node.version)") {
    throw "Node version does not match runtime.lock.json."
}
Assert-ExitCode "Node version check"
Assert-LockedFile $NodeExecutable $lock.node.files[0]

if (-not $FfmpegBinDirectory) {
    $FfmpegBinDirectory = Split-Path -Parent (Get-Command ffmpeg.exe -ErrorAction Stop).Source
}
$FfmpegBinDirectory = [IO.Path]::GetFullPath($FfmpegBinDirectory)
$ffmpegExecutable = Join-Path $FfmpegBinDirectory "ffmpeg.exe"
$ffmpegVersion = (& $ffmpegExecutable -version 2>&1 | Select-Object -First 1).ToString()
Assert-ExitCode "FFmpeg version check"
if (-not $ffmpegVersion.StartsWith([string]$lock.ffmpeg.version_prefix, [StringComparison]::Ordinal)) {
    throw "FFmpeg version does not match runtime.lock.json."
}
foreach ($expected in $lock.ffmpeg.files) {
    Assert-LockedFile (Join-Path $FfmpegBinDirectory ([string]$expected.name)) $expected
}
$ffmpegLicense = Join-Path (Split-Path -Parent $FfmpegBinDirectory) ([string]$lock.ffmpeg.license.name)
Assert-LockedFile $ffmpegLicense $lock.ffmpeg.license

$project = Get-Content -Raw -LiteralPath (Join-Path $root "pyproject.toml") | python -c "import sys,tomllib; print(tomllib.loads(sys.stdin.read())['project']['version'])"
Assert-ExitCode "Project version read"
$version = $project.Trim()
$parts = @($version.Split('.') | ForEach-Object { [int]$_ })
while ($parts.Count -lt 4) { $parts += 0 }
$versionFile = Join-Path $stage "version-info.txt"
$versionTemplate = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($($parts[0]), $($parts[1]), $($parts[2]), $($parts[3])), prodvers=($($parts[0]), $($parts[1]), $($parts[2]), $($parts[3])), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('080404B0', [StringStruct('CompanyName', 'ChatWechat'), StringStruct('FileDescription', 'ChatWechat 本地微信导出'), StringStruct('FileVersion', '$version'), StringStruct('InternalName', 'ChatWechat'), StringStruct('OriginalFilename', 'ChatWechat.exe'), StringStruct('ProductName', 'ChatWechat'), StringStruct('ProductVersion', '$version')])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])]
)
"@
Set-Content -LiteralPath $versionFile -Value $versionTemplate -Encoding UTF8

$dist = Join-Path $stage "dist"
$work = Join-Path $stage "work"
$env:CHATWECHAT_VERSION_FILE = $versionFile
Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $root "packaging\ChatWechat.spec")
    Assert-ExitCode "PyInstaller build"
}
finally {
    Remove-Item Env:CHATWECHAT_VERSION_FILE -ErrorAction SilentlyContinue
    Pop-Location
}

$application = Join-Path $dist "ChatWechat"
$nodeTarget = Join-Path $application "runtime\node"
$ffmpegTarget = Join-Path $application "runtime\ffmpeg"
New-Item -ItemType Directory -Path $nodeTarget, $ffmpegTarget | Out-Null
Copy-Item -LiteralPath $NodeExecutable -Destination (Join-Path $nodeTarget "node.exe")
Copy-Item -LiteralPath (Join-Path $root "packaging\NODE-LICENSE.txt") -Destination (Join-Path $nodeTarget "LICENSE.txt")
foreach ($expected in $lock.ffmpeg.files) {
    Copy-Item -LiteralPath (Join-Path $FfmpegBinDirectory ([string]$expected.name)) -Destination $ffmpegTarget
}
Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $ffmpegTarget "LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $root "THIRD_PARTY_NOTICES.md") -Destination $application
Copy-Item -LiteralPath (Join-Path $root "packaging\INSTALL-README.txt") -Destination (Join-Path $application "README.txt")
Copy-Item -LiteralPath (Join-Path $root "packaging\runtime.lock.json") -Destination $application

$selfTestPath = Join-Path $stage "self-test.json"
$isolatedLocalAppData = Join-Path $stage "isolated-localappdata"
New-Item -ItemType Directory -Path $isolatedLocalAppData | Out-Null
$savedPath = $env:PATH
$savedLocalAppData = $env:LOCALAPPDATA
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:LOCALAPPDATA = $isolatedLocalAppData
    $process = Start-Process -FilePath (Join-Path $application "ChatWechat.exe") -ArgumentList @("--self-test", "--json", "--output", $selfTestPath) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "Packaged self-test failed with exit code $($process.ExitCode)."
    }
}
finally {
    $env:PATH = $savedPath
    $env:LOCALAPPDATA = $savedLocalAppData
}
$selfTest = Get-Content -Raw -LiteralPath $selfTestPath | ConvertFrom-Json
if (-not $selfTest.ok -or -not $selfTest.frozen) {
    throw "Packaged self-test did not validate frozen mode."
}
if (-not $selfTest.runtime_tools.node.bundled -or -not $selfTest.runtime_tools.ffmpeg.bundled) {
    throw "Packaged self-test used a system runtime instead of bundled tools."
}

$result = [ordered]@{
    version = $version
    staging_root = $stage
    application_root = $application
    executable = (Join-Path $application "ChatWechat.exe")
    self_test = $selfTestPath
}
$resultPath = Join-Path $stage "build-result.json"
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding UTF8
Write-Output $resultPath
