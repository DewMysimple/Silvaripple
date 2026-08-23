[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

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
    corepack pnpm@10.34.5 --dir frontend typecheck
    Assert-ExitCode "TypeScript typecheck"
    corepack pnpm@10.34.5 --dir frontend build
    Assert-ExitCode "React production build"

    python wiki-memory/工具/memory_lint.py index
    Assert-ExitCode "Memory index"
    python wiki-memory/工具/memory_lint.py check
    Assert-ExitCode "Memory lint"
}
finally {
    $env:CI = $savedCi
    Pop-Location
}
