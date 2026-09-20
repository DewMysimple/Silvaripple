[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$root = [IO.Path]::GetFullPath($RepositoryRoot)
Push-Location $root
$savedCi = $env:CI
try {
    $env:CI = "true"
    python -m pytest -q
    Assert-ExitCode "Python tests"

    if (-not $SkipFrontendInstall) {
        corepack pnpm@10.34.5 --dir frontend install --frozen-lockfile
        Assert-ExitCode "Frontend dependency verification"
    }
    corepack pnpm@10.34.5 --dir frontend test
    Assert-ExitCode "React tests"
    corepack pnpm@10.34.5 --dir frontend format:check
    Assert-ExitCode "Frontend formatting"
    corepack pnpm@10.34.5 --dir frontend typecheck
    Assert-ExitCode "TypeScript typecheck"
    corepack pnpm@10.34.5 --dir frontend build
    Assert-ExitCode "React production build"
    corepack pnpm@10.34.5 --dir frontend test:e2e
    Assert-ExitCode "Workbench browser regression"

    cargo fmt --manifest-path frontend/src-tauri/Cargo.toml -- --check
    Assert-ExitCode "Rust formatting"
    cargo test --manifest-path frontend/src-tauri/Cargo.toml
    Assert-ExitCode "Tauri Rust tests"
    cargo check --manifest-path frontend/src-tauri/Cargo.toml
    Assert-ExitCode "Tauri Rust check"

    $memoryLint = Get-ChildItem -LiteralPath (Join-Path $root "wiki-memory") -Filter "memory_lint.py" -File -Recurse | Select-Object -First 1
    if (-not $memoryLint) { throw "Memory lint tool was not found." }
    python $memoryLint.FullName index
    Assert-ExitCode "Memory index"
    python $memoryLint.FullName check
    Assert-ExitCode "Memory lint"
}
finally {
    $env:CI = $savedCi
    Pop-Location
}
