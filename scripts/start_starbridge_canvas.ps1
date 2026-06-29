[CmdletBinding()]
param(
    [string]$ProjectDir = (Get-Location).Path,
    [string]$CanvasDir = "",
    [int]$Port = 43217,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $RepoRoot "examples\starbridge_canvas"
$PackageFile = Join-Path $AppDir "package.json"

if (-not (Test-Path -LiteralPath $PackageFile)) {
    throw "StarBridge Canvas package was not found: $PackageFile"
}

$ResolvedProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path

if ([string]::IsNullOrWhiteSpace($CanvasDir)) {
    $ResolvedCanvasDir = Join-Path $ResolvedProjectDir "canvas"
} else {
    $ResolvedCanvasDir = $CanvasDir
}

New-Item -ItemType Directory -Force -Path $ResolvedCanvasDir | Out-Null
$ResolvedCanvasDir = (Resolve-Path -LiteralPath $ResolvedCanvasDir).Path

$env:STARBRIDGE_CANVAS_PROJECT_DIR = $ResolvedProjectDir
$env:STARBRIDGE_CANVAS_DIR = $ResolvedCanvasDir
$env:STARBRIDGE_CANVAS_URL = "http://127.0.0.1:$Port"

# Compatibility for tools that still know the original canvas prototype name.
$env:COWART_PROJECT_DIR = $ResolvedProjectDir
$env:COWART_CANVAS_DIR = $ResolvedCanvasDir
$env:COWART_URL = $env:STARBRIDGE_CANVAS_URL

$TldrawPackage = Join-Path $AppDir "node_modules\tldraw\package.json"
if (-not $NoInstall -and -not (Test-Path -LiteralPath $TldrawPackage)) {
    & npm.cmd --prefix $AppDir install --package-lock=false
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host "StarBridge Canvas: $env:STARBRIDGE_CANVAS_URL"
Write-Host "Canvas data: $ResolvedCanvasDir"

& npm.cmd --prefix $AppDir run dev -- --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
