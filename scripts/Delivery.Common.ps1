# Shared, side-effect-free helpers for the Windows portable delivery pipeline.
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    $childFull = [IO.Path]::GetFullPath($Child)
    if (-not $childFull.StartsWith($parentFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside the expected parent: $childFull"
    }
    $cursor = $childFull
    while ($cursor.Length -ge $parentFull.Length) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Refusing to operate through a filesystem link: $cursor"
        }
        $cursor = Split-Path -Parent $cursor
    }
}

function Remove-BuildDirectory([string]$Parent, [string]$Path) {
    Assert-ChildPath $Parent $Path
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
}

function Assert-LockedFile([string]$Path, [object]$Expected) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Name -cne [string]$Expected.name -or $item.Length -ne [int64]$Expected.size) {
        throw "Runtime file does not match the lock: $($item.Name)."
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
    if ($actual -cne [string]$Expected.sha256) { throw "Runtime SHA-256 mismatch: $($item.Name)." }
}

function Copy-VerifiedRuntime([string]$RepositoryRoot, [string]$NodeExecutable, [string]$FfmpegBinDirectory) {
    $lock = Get-Content -Raw -LiteralPath (Join-Path $RepositoryRoot "packaging\runtime.lock.json") | ConvertFrom-Json
    if (-not $NodeExecutable) { $NodeExecutable = (Get-Command node.exe -ErrorAction Stop).Source }
    if ((& $NodeExecutable --version).Trim() -ne "v$($lock.node.version)") { throw "Node version does not match runtime.lock.json." }
    Assert-LockedFile $NodeExecutable $lock.node.files[0]
    if (-not $FfmpegBinDirectory) { $FfmpegBinDirectory = Split-Path -Parent (Get-Command ffmpeg.exe -ErrorAction Stop).Source }
    $ffmpegExecutable = Join-Path $FfmpegBinDirectory "ffmpeg.exe"
    $ffmpegVersion = (& $ffmpegExecutable -version 2>&1 | Select-Object -First 1).ToString()
    if (-not $ffmpegVersion.StartsWith([string]$lock.ffmpeg.version_prefix, [StringComparison]::Ordinal)) { throw "FFmpeg version does not match runtime.lock.json." }
    foreach ($expected in $lock.ffmpeg.files) { Assert-LockedFile (Join-Path $FfmpegBinDirectory ([string]$expected.name)) $expected }
    $ffmpegLicense = Join-Path (Split-Path -Parent $FfmpegBinDirectory) ([string]$lock.ffmpeg.license.name)
    Assert-LockedFile $ffmpegLicense $lock.ffmpeg.license

    $resourceRoot = Join-Path $RepositoryRoot "frontend\src-tauri\resources"
    $runtimeRoot = Join-Path $resourceRoot "runtime"
    Remove-BuildDirectory $resourceRoot $runtimeRoot
    $nodeTarget = Join-Path $runtimeRoot "node"
    $ffmpegTarget = Join-Path $runtimeRoot "ffmpeg"
    New-Item -ItemType Directory -Path $nodeTarget, $ffmpegTarget | Out-Null
    Copy-Item -LiteralPath $NodeExecutable -Destination (Join-Path $nodeTarget "node.exe")
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot "packaging\NODE-LICENSE.txt") -Destination (Join-Path $nodeTarget "LICENSE.txt")
    foreach ($expected in $lock.ffmpeg.files) { Copy-Item -LiteralPath (Join-Path $FfmpegBinDirectory ([string]$expected.name)) -Destination $ffmpegTarget }
    Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $ffmpegTarget "LICENSE.txt")
}

function Copy-TauriResources([string]$TauriRoot, [string]$ApplicationRoot) {
    $bundle = Get-Content -Raw -LiteralPath (Join-Path $TauriRoot "tauri.bundle.conf.json") | ConvertFrom-Json
    foreach ($entry in $bundle.bundle.resources.PSObject.Properties) {
        $source = [IO.Path]::GetFullPath((Join-Path $TauriRoot $entry.Name)).TrimEnd('\', '/')
        $target = [IO.Path]::GetFullPath((Join-Path $ApplicationRoot ([string]$entry.Value))).TrimEnd('\', '/')
        Assert-ChildPath $ApplicationRoot $target
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Recurse
    }
}

function Write-PackageManifest([string]$ApplicationRoot, [string]$Version, [string]$Commit) {
    $prefix = [IO.Path]::GetFullPath($ApplicationRoot).TrimEnd('\') + '\'
    $files = @(Get-ChildItem -LiteralPath $ApplicationRoot -File -Recurse | Where-Object { $_.Name -ne "build-info.json" } | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($prefix.Length).Replace('\', '/')
            size = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    [ordered]@{ version = $Version; commit = $Commit; files = $files } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ApplicationRoot "build-info.json") -Encoding UTF8
}

function Assert-PackageManifest([string]$ApplicationRoot) {
    $manifestPath = Join-Path $ApplicationRoot "build-info.json"
    $manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
    $actualFiles = @(Get-ChildItem -LiteralPath $ApplicationRoot -File -Recurse | Where-Object { $_.FullName -ne $manifestPath })
    if ($actualFiles.Count -ne @($manifest.files).Count) { throw "Package contains missing or unexpected files." }
    $seen = @{}
    foreach ($file in $manifest.files) {
        $path = Join-Path $ApplicationRoot ([string]$file.path)
        Assert-ChildPath $ApplicationRoot $path
        $normalizedPath = [IO.Path]::GetFullPath($path)
        if ($seen.ContainsKey($normalizedPath)) { throw "Package manifest contains a duplicate file." }
        $seen[$normalizedPath] = $true
        $item = Get-Item -LiteralPath $path -ErrorAction Stop
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($item.Length -ne [long]$file.size -or $hash -cne [string]$file.sha256) { throw "Package integrity check failed: $($file.path)" }
    }
}

function Invoke-IsolatedProcess([string]$Executable, [string]$Arguments, [string]$TestRoot, [int]$TimeoutMilliseconds = 90000) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $TestRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.Environment["LOCALAPPDATA"] = Join-Path $TestRoot "localappdata"
    $info.Environment["APPDATA"] = Join-Path $TestRoot "appdata"
    $info.Environment["PATH"] = "$env:SystemRoot\System32;$env:SystemRoot"
    foreach ($name in @("CHATWECHAT_RESOURCE_DIR", "CHATWECHAT_BACKEND", "CHATWECHAT_PYTHON", "PYTHONPATH", "PYTHONHOME")) { $info.Environment.Remove($name) | Out-Null }
    $process = [Diagnostics.Process]::Start($info)
    # Drain both pipes concurrently; a verbose component must not fill one pipe
    # while the verifier waits on the other or on process completion.
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            # PyInstaller can own a worker process. Stop that exact tree too,
            # otherwise a timeout could leave the extracted application locked.
            & (Join-Path $env:SystemRoot "System32\taskkill.exe") /PID $process.Id /T /F 2>&1 | Out-Null
            if (-not $process.HasExited) { $process.Kill() }
            $process.WaitForExit(5000) | Out-Null
            throw "Portable component timed out: $([IO.Path]::GetFileName($Executable))."
        }
        if (-not $stdout.Wait(5000) -or -not $stderr.Wait(5000)) { throw "Portable component output did not close: $([IO.Path]::GetFileName($Executable))." }
        if ($process.ExitCode -ne 0) { throw "Portable component failed with exit code $($process.ExitCode): $([IO.Path]::GetFileName($Executable)). $($stderr.Result.Trim())" }
        return [pscustomobject]@{ stdout = $stdout.Result; stderr = $stderr.Result }
    }
    finally { $process.Dispose() }
}

function Invoke-PortableSelfTest([string]$ApplicationRoot, [string]$TestRoot) {
    Assert-PackageManifest $ApplicationRoot
    foreach ($file in @("ChatWechat.exe", "chatwechat-backend.exe", "THIRD_PARTY_NOTICES.md", "licenses\silk-wasm-LICENSE.txt", "runtime\node\node.exe", "runtime\node\LICENSE.txt", "runtime\ffmpeg\ffmpeg.exe", "runtime\ffmpeg\LICENSE.txt")) {
        if (-not (Test-Path -LiteralPath (Join-Path $ApplicationRoot $file) -PathType Leaf)) { throw "Portable application is missing: $file" }
    }
    New-Item -ItemType Directory -Force -Path $TestRoot | Out-Null
    $node = Invoke-IsolatedProcess (Join-Path $ApplicationRoot "runtime\node\node.exe") "--version" $TestRoot 20000
    $ffmpeg = Invoke-IsolatedProcess (Join-Path $ApplicationRoot "runtime\ffmpeg\ffmpeg.exe") "-version" $TestRoot 20000
    if ($node.stdout.Trim() -notmatch '^v[0-9]+\.' -or $ffmpeg.stdout -notmatch '^ffmpeg version ') { throw "Bundled runtime version probes returned unexpected output." }
    $output = Join-Path $TestRoot "backend-self-test.json"
    Invoke-IsolatedProcess (Join-Path $ApplicationRoot "chatwechat-backend.exe") "--self-test --json --output `"$output`"" $TestRoot | Out-Null
    $result = Get-Content -Raw -LiteralPath $output -Encoding UTF8 | ConvertFrom-Json
    if (-not $result.ok -or -not $result.frozen -or -not $result.runtime_tools.node.bundled -or -not $result.runtime_tools.ffmpeg.bundled) {
        throw "Portable backend did not pass isolated, bundled-runtime self-test."
    }
    return $output
}

function Assert-ReplaceableApplication([string]$ApplicationRoot) {
    $ApplicationRoot = [IO.Path]::GetFullPath($ApplicationRoot).TrimEnd('\', '/')
    $manifestPath = Join-Path $ApplicationRoot "build-info.json"
    if (-not (Test-Path -LiteralPath $ApplicationRoot -PathType Container) -or -not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Existing application has no recognizable build manifest; preserve it before publishing: $ApplicationRoot"
    }
    Assert-ChildPath $ApplicationRoot $manifestPath
    $manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
    if (-not $manifest.version -or -not $manifest.commit -or -not @($manifest.files).Count) {
        throw "Existing application has no recognizable build manifest: $ApplicationRoot"
    }
    $allowedFiles = @{ $manifestPath = $true }
    $allowedDirectories = @{}
    foreach ($file in $manifest.files) {
        if (-not $file.path -or [IO.Path]::IsPathRooted([string]$file.path) -or [string]$file.sha256 -notmatch '^[0-9a-f]{64}$' -or [long]$file.size -lt 0) {
            throw "Existing application build manifest contains an invalid file entry."
        }
        $path = [IO.Path]::GetFullPath((Join-Path $ApplicationRoot ([string]$file.path)))
        Assert-ChildPath $ApplicationRoot $path
        if ($allowedFiles.ContainsKey($path)) { throw "Existing application build manifest contains duplicate paths." }
        $allowedFiles[$path] = $true
        $directory = Split-Path -Parent $path
        while ($directory -ne $ApplicationRoot) {
            $allowedDirectories[$directory] = $true
            $directory = Split-Path -Parent $directory
        }
    }
    if (-not $allowedFiles.ContainsKey((Join-Path $ApplicationRoot "ChatWechat.exe"))) {
        throw "Existing build manifest does not identify the ChatWechat application."
    }
    # Enumerate one level at a time, rejecting links before traversing a directory.
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($ApplicationRoot)
    while ($pending.Count) {
        foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Existing application contains a filesystem link: $($item.FullName)" }
            $known = if ($item.PSIsContainer) { $allowedDirectories.ContainsKey($item.FullName) } else { $allowedFiles.ContainsKey($item.FullName) }
            if (-not $known) { throw "Existing application contains an unrecognized file or directory; preserve it before publishing: $($item.FullName)" }
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
        }
    }
}

function Publish-DeliveryDirectory([string]$Candidate, [string]$Destination, [scriptblock]$Verify) {
    $parent = Split-Path -Parent $Destination
    Assert-ChildPath $parent $Candidate
    Assert-ChildPath $parent $Destination
    if (Test-Path -LiteralPath $Destination) {
        $unexpected = @(Get-ChildItem -LiteralPath $Destination -Force | Where-Object { $_.Name -notin @("ChatWechat", "ChatWechat.zip") })
        if ($unexpected.Count) { throw "Delivery directory contains unrecognized files; keep them safe before publishing: $Destination" }
        $oldApplication = Join-Path $Destination "ChatWechat"
        $oldArchive = Join-Path $Destination "ChatWechat.zip"
        Assert-ChildPath $Destination $oldApplication
        Assert-ChildPath $Destination $oldArchive
        if ((Test-Path -LiteralPath $oldArchive) -and -not (Test-Path -LiteralPath $oldArchive -PathType Leaf)) { throw "Existing delivery archive is not a file: $oldArchive" }
        if (Test-Path -LiteralPath $oldApplication) { Assert-ReplaceableApplication $oldApplication }
    }
    $backup = Join-Path $parent (".dist.backup-" + [guid]::NewGuid().ToString("N"))
    Assert-ChildPath $parent $backup
    $backedUp = $false
    $published = $false
    try {
        if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $backup; $backedUp = $true }
        Move-Item -LiteralPath $Candidate -Destination $Destination
        $published = $true
        & $Verify $Destination
    }
    catch {
        if ($published) { Remove-BuildDirectory $parent $Destination }
        if ($backedUp) { Move-Item -LiteralPath $backup -Destination $Destination }
        throw
    }
    if ($backedUp) { Remove-BuildDirectory $parent $backup }
}
