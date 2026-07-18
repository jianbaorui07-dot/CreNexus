[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$RepositoryUrl,
    [string]$Destination = "StarBridge",
    [ValidateSet("auto", "core", "standard", "all")]
    [string]$Profile = "auto",
    [switch]$SkipNode,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

if ($RepositoryUrl -notmatch "^https?://") {
    throw "RepositoryUrl must be an HTTPS or HTTP Git URL."
}

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    throw "Git was not found. Install Git, then rerun this command."
}

$destinationPath = if ([System.IO.Path]::IsPathRooted($Destination)) {
    [System.IO.Path]::GetFullPath($Destination)
} else {
    [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Destination))
}
$steps = [System.Collections.ArrayList]::new()

if (Test-Path -LiteralPath $destinationPath) {
    if (-not (Test-Path -LiteralPath (Join-Path $destinationPath ".git"))) {
        throw "Destination exists but is not a Git checkout: $destinationPath"
    }
    [void]$steps.Add([ordered]@{ name = "reuse existing checkout"; status = "completed"; detail = $destinationPath })
} elseif ($DryRun) {
    [void]$steps.Add([ordered]@{ name = "clone repository"; status = "planned"; detail = "$RepositoryUrl -> $destinationPath" })
} else {
    & $git.Source clone --depth 1 $RepositoryUrl $destinationPath
    if ($LASTEXITCODE -ne 0) { throw "Git clone failed (exit $LASTEXITCODE)." }
    [void]$steps.Add([ordered]@{ name = "clone repository"; status = "completed"; detail = $destinationPath })
}

$quickstart = Join-Path $destinationPath "scripts\quickstart.ps1"
if (-not $DryRun -and -not (Test-Path -LiteralPath $quickstart)) {
    throw "The checkout does not contain scripts\quickstart.ps1: $destinationPath"
}

if ($DryRun) {
    [void]$steps.Add([ordered]@{ name = "run quickstart"; status = "planned"; detail = "$quickstart -Profile $Profile" })
    $result = [ordered]@{ ok = $true; repository = $RepositoryUrl; checkout = $destinationPath; steps = @($steps) }
    if ($Json) { $result | ConvertTo-Json -Depth 8 } else { $result | Format-List }
    exit 0
}

$quickArgs = @("-Profile", $Profile)
if ($SkipNode) { $quickArgs += "-SkipNode" }
if ($Json) { $quickArgs += "-Json" }
& powershell.exe -ExecutionPolicy Bypass -File $quickstart @quickArgs
if ($LASTEXITCODE -ne 0) { throw "StarBridge quickstart failed (exit $LASTEXITCODE)." }
