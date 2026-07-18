[CmdletBinding()]
param(
    [ValidateSet("auto", "core", "standard", "all")]
    [string]$Profile = "auto",
    [switch]$SkipNode,
    [switch]$SkipCodexConfig,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$quickstart = Join-Path $PSScriptRoot "scripts\quickstart.ps1"
if (-not (Test-Path -LiteralPath $quickstart)) {
    throw "Missing scripts\quickstart.ps1"
}

$quickstartParameters = @{ Profile = $Profile }
if ($SkipNode) { $quickstartParameters.SkipNode = $true }
if ($SkipCodexConfig) { $quickstartParameters.SkipCodexConfig = $true }
if ($DryRun) { $quickstartParameters.DryRun = $true }
if ($Json) { $quickstartParameters.Json = $true }

try {
    & $quickstart @quickstartParameters
    exit 0
}
catch {
    [Console]::Error.WriteLine("StarBridge bootstrap failed: $($_.Exception.Message)")
    exit 1
}
