param(
    [string]$ReferenceId = "reference",
    [string]$InputPath = "",
    [string]$OutputDir = "examples/output/illustrator",
    [int]$MaxColors = 64,
    [double]$PathFitting = 1.5,
    [int]$MinArea = 2,
    [double]$PreprocessBlur = 0.0,
    [switch]$IgnoreWhite,
    [switch]$DisableOutputToSwatches,
    [bool]$DryRun = $true,
    [switch]$ConfirmWrite,
    [switch]$ConfirmExport
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Resolve-SandboxDir {
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
    return $candidate
}

function Convert-ToRepoRelative {
    param([string]$RepoRoot, [string]$PathValue)
    $full = [System.IO.Path]::GetFullPath($PathValue)
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($full -eq $RepoRoot -or $full.StartsWith($RepoRoot + $separator, [System.StringComparison]::OrdinalIgnoreCase)) {
        return ($full.Substring($RepoRoot.Length).TrimStart("\", "/") -replace "\\", "/")
    }
    return "<REDACTED_PATH>"
}

function Write-JsonResult {
    param([hashtable]$Result)
    $Result | ConvertTo-Json -Depth 16
}

function Test-TraceSettings {
    if ($ReferenceId -notmatch '^[a-z0-9][a-z0-9_-]{0,63}$') {
        throw "ReferenceId must use lowercase letters, digits, underscore, or hyphen."
    }
    if ($MaxColors -lt 2 -or $MaxColors -gt 256) {
        throw "MaxColors must be between 2 and 256."
    }
    if ($PathFitting -lt 0 -or $PathFitting -gt 10) {
        throw "PathFitting must be between 0 and 10."
    }
    if ($MinArea -lt 1 -or $MinArea -gt 1000) {
        throw "MinArea must be between 1 and 1000."
    }
    if ($PreprocessBlur -lt 0 -or $PreprocessBlur -gt 2) {
        throw "PreprocessBlur must be between 0 and 2."
    }
}

if ($ConfirmWrite -or $ConfirmExport) {
    $DryRun = $false
}

Test-TraceSettings
$repoRoot = Get-RepoRoot
$outDir = Resolve-SandboxDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$aiPath = Join-Path $outDir ($ReferenceId + ".ai")
$svgPath = Join-Path $outDir ($ReferenceId + ".svg")
$pngPath = Join-Path $outDir ($ReferenceId + ".png")
$jsxPath = Join-Path $repoRoot "examples\illustrator_bridge\jsx\color_vectorize.jsx"

$plan = @{
    ok = $true
    bridge = "illustrator"
    task = "color_vectorize"
    verdict = "planned"
    reference_id = $ReferenceId
    dry_run = [bool]$DryRun
    confirm_write = [bool]$ConfirmWrite
    confirm_export = [bool]$ConfirmExport
    trace = @{
        mode = "color"
        fills = $true
        strokes = $false
        max_colors = $MaxColors
        path_fitting = $PathFitting
        min_area = $MinArea
        preprocess_blur = $PreprocessBlur
        ignore_white = [bool]$IgnoreWhite
        output_to_swatches = -not [bool]$DisableOutputToSwatches
    }
    outputs = @{
        illustrator_document = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $aiPath
        svg = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $svgPath
        preview_png = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath
    }
    safety = @{
        input_policy = "single_explicit_user_file"
        recursive_scan = $false
        cloud_upload = $false
        arbitrary_script = $false
        visual_review_required = $true
    }
    warnings = @()
    next_steps = @("Review the plan, then provide one explicit PNG/JPEG and both confirmations.")
}

if ($DryRun) {
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmWrite) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Refusing real Illustrator vector write without confirm_write=true.")
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmExport) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Refusing real Illustrator vector export without confirm_export=true.")
    Write-JsonResult $plan
    exit 0
}

if ([string]::IsNullOrWhiteSpace($InputPath) -or -not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("The explicitly supplied input file was not found.")
    Write-JsonResult $plan
    exit 0
}

$inputFile = (Resolve-Path -LiteralPath $InputPath).Path
$extension = [System.IO.Path]::GetExtension($inputFile).ToLowerInvariant()
if ($extension -notin @(".png", ".jpg", ".jpeg")) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Input must be one PNG or JPEG file.")
    Write-JsonResult $plan
    exit 0
}

try {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $inputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $inputFile).Hash.ToLowerInvariant()
    $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Illustrator.Application")
    $config = @{
        referenceId = $ReferenceId
        inputPath = $inputFile
        inputHash = $inputHash
        aiPath = $aiPath
        svgPath = $svgPath
        pngPath = $pngPath
        aiPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $aiPath
        svgPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $svgPath
        pngPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $pngPath
        maxColors = $MaxColors
        pathFitting = $PathFitting
        minArea = $MinArea
        preprocessBlur = $PreprocessBlur
        ignoreWhite = [bool]$IgnoreWhite
        outputToSwatches = -not [bool]$DisableOutputToSwatches
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -LiteralPath $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $raw | ConvertFrom-Json | ConvertTo-Json -Depth 16
} catch {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Could not run the guarded color trace in the active Illustrator session.")
    $plan.error_type = $_.Exception.GetType().Name
    $plan.next_steps = @(
        "Start an authorized Illustrator desktop session.",
        "Keep the input explicit and the output inside examples/output/illustrator.",
        "Run the dry-run plan again before retrying."
    )
    Write-JsonResult $plan
    exit 0
}
