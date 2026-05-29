param(
    [string]$OutputDir = "examples/output/illustrator",
    [bool]$DryRun = $true,
    [switch]$ConfirmExport
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-SandboxDir {
    param([string]$RepoRoot, [string]$RequestedDir)
    $allowed = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "examples\output\illustrator"))
    if ([System.IO.Path]::IsPathRooted($RequestedDir)) {
        $candidate = [System.IO.Path]::GetFullPath($RequestedDir)
    } else {
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RequestedDir))
    }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($candidate -ne $allowed -and -not $candidate.StartsWith($allowed + $separator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "OutputDir must stay inside examples/output/illustrator."
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
$aiPath = Join-Path $outDir "starbridge_ai_demo.ai"
$svgPath = Join-Path $outDir "starbridge_ai_demo.svg"
$pngPath = Join-Path $outDir "starbridge_ai_demo.png"
$pdfPath = Join-Path $outDir "starbridge_ai_demo.pdf"
$jsxPath = Join-Path $repoRoot "examples\illustrator_bridge\jsx\export_demo_assets.jsx"

$result = @{
    ok = $true
    bridge = "illustrator"
    task = "export_demo_assets"
    dry_run = [bool]$DryRun
    confirm_export = [bool]$ConfirmExport
    exported_files = @(
        Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $svgPath,
        Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath,
        Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pdfPath
    )
    svg_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $svgPath
    png_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath
    pdf_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pdfPath
    warnings = @()
    next_steps = @("Run with -ConfirmExport after creating the sandbox Illustrator demo document.")
}

if ($DryRun) {
    Write-JsonResult $result
    exit 0
}

if (-not $ConfirmExport) {
    $result.ok = $false
    $result.warnings = @("Refusing real Illustrator export without confirm_export=true.")
    $result.next_steps = @("Run the dry-run plan first, then use -ConfirmExport for sandbox output.")
    Write-JsonResult $result
    exit 0
}

try {
    $app = New-Object -ComObject Illustrator.Application
    $config = @{
        demoAiPath = $aiPath
        demoAiPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $aiPath
        svgPath = $svgPath
        pngPath = $pngPath
        pdfPath = $pdfPath
        svgPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $svgPath
        pngPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath
        pdfPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pdfPath
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -Path $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $raw | ConvertFrom-Json | ConvertTo-Json -Depth 12
} catch {
    $result.ok = $false
    $result.warnings = @("Could not export Illustrator demo assets through COM.")
    $result.next_steps = @(
        "Create the sandbox demo document first.",
        "Keep the active document as starbridge_ai_demo.ai or leave the sandbox demo in examples/output/illustrator.",
        "Run npm.cmd run illustrator:demo:plan to inspect the safe plan."
    )
    $result.error_type = $_.Exception.GetType().Name
    Write-JsonResult $result
    exit 0
}
