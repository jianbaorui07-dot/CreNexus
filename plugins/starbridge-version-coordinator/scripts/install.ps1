param(
    [switch]$DryRun,
    [switch]$SkipMarketplaceAdd
)

$ErrorActionPreference = "Stop"

$pluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $pluginRoot "..\..")
$marketplacePath = Join-Path $repoRoot ".agents\plugins\marketplace.json"
$serverPath = Join-Path $pluginRoot "scripts\version_coordinator_mcp.py"

if (-not (Test-Path -LiteralPath $marketplacePath)) {
    throw "Marketplace manifest not found: $marketplacePath"
}
if (-not (Test-Path -LiteralPath $serverPath)) {
    throw "Coordinator server not found: $serverPath"
}

$python = Get-Command python -ErrorAction SilentlyContinue
$codex = Get-Command codex -ErrorAction SilentlyContinue
$plan = [ordered]@{
    plugin = "starbridge-version-coordinator"
    marketplace = "starbridge-local"
    repo_root = $repoRoot.Path
    python_found = $null -ne $python
    codex_found = $null -ne $codex
    actions = @(
        "python plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py self-test",
        "codex plugin marketplace add <repo-root>",
        "codex plugin add starbridge-version-coordinator@starbridge-local",
        "start a new Codex task"
    )
}

if ($DryRun) {
    $plan | ConvertTo-Json -Depth 5
    exit 0
}

if (-not $python) {
    throw "Python was not found. Install Python 3.10+ and retry."
}
if (-not $codex) {
    throw "Codex CLI was not found. Install or repair Codex CLI and retry."
}

& $python.Source $serverPath self-test
if ($LASTEXITCODE -ne 0) {
    throw "Coordinator self-test failed."
}

if (-not $SkipMarketplaceAdd) {
    & $codex.Source plugin marketplace add $repoRoot.Path
    if ($LASTEXITCODE -ne 0) {
        throw "Marketplace add failed. If starbridge-local already exists, rerun with -SkipMarketplaceAdd."
    }
}

& $codex.Source plugin add "starbridge-version-coordinator@starbridge-local"
if ($LASTEXITCODE -ne 0) {
    throw "Plugin install failed."
}

Write-Host "Installed starbridge-version-coordinator. Start a new Codex task to load its tools."
