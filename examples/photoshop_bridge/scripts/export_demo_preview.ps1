param(
    [string]$OutputDir = "examples/output/photoshop",
    [bool]$DryRun = $true,
    [switch]$ConfirmExport
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-SandboxDir {
    param([string]$RepoRoot, [string]$RequestedDir)
    $allowed = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "examples\output\photoshop"))
    if ([System.IO.Path]::IsPathRooted($RequestedDir)) {
        $candidate = [System.IO.Path]::GetFullPath($RequestedDir)
    } else {
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RequestedDir))
    }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($candidate -ne $allowed -and -not $candidate.StartsWith($allowed + $separator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "OutputDir must stay inside examples/output/photoshop."
    }
    New-Item -ItemType Directory -Force -Path $candidate | Out-Null
    return $candidate
}

function Convert-ToRepoRelative {
    param([string]$RepoRoot, [string]$PathValue)
    $full = [System.IO.Path]::GetFullPath($PathValue)
    if ($full.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return ($full.Substring($RepoRoot.Length).TrimStart("\","/") -replace "\\", "/")
    }
    return "<REDACTED_PATH>"
}

function Write-JsonResult {
    param([hashtable]$Result)
    $Result | ConvertTo-Json -Depth 12
}

if ($ConfirmExport) {
    $DryRun = $false
}

$repoRoot = Get-RepoRoot
$outDir = Get-SandboxDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$psdPath = Join-Path $outDir "starbridge_ps_demo.psd"
$pngPath = Join-Path $outDir "starbridge_ps_demo.png"
$jpgPath = Join-Path $outDir "starbridge_ps_demo.jpg"
$jsxPath = Join-Path $repoRoot "examples\photoshop_bridge\jsx\export_demo_preview.jsx"

$result = @{
    ok = $true
    bridge = "photoshop"
    task = "export_demo_preview"
    dry_run = [bool]$DryRun
    confirm_export = [bool]$ConfirmExport
    exported_files = @(
        Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath,
        Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jpgPath
    )
    width = 1080
    height = 1080
    layer_count = $null
    warnings = @()
    next_steps = @("Run with -ConfirmExport after creating the sandbox Photoshop demo PSD.")
}

if ($DryRun) {
    Write-JsonResult $result
    exit 0
}

if (-not $ConfirmExport) {
    $result.ok = $false
    $result.warnings = @("Refusing real Photoshop export without confirm_export=true.")
    $result.next_steps = @("Run the dry-run plan first, then use -ConfirmExport for sandbox output.")
    Write-JsonResult $result
    exit 0
}

try {
    $app = New-Object -ComObject Photoshop.Application
    $config = @{
        demoPsdPath = $psdPath
        demoPsdPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $psdPath
        pngPath = $pngPath
        jpgPath = $jpgPath
        pngPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath
        jpgPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jpgPath
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -Path $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $raw | ConvertFrom-Json | ConvertTo-Json -Depth 12
} catch {
    $result.ok = $false
    $result.warnings = @("Could not export Photoshop demo previews through COM.")
    $result.next_steps = @(
        "Create the sandbox demo PSD first.",
        "Keep the active document as starbridge_ps_demo.psd or leave the sandbox PSD in examples/output/photoshop.",
        "Run npm.cmd run photoshop:demo:plan to inspect the safe plan."
    )
    $result.error_type = $_.Exception.GetType().Name
    Write-JsonResult $result
    exit 0
}
