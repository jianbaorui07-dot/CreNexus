param(
    [string]$ReferenceId = "reference",
    [string]$InputPath = "",
    [string]$OutputDir = "examples/output/photoshop",
    [int]$MaxDimension = 4096,
    [int]$MedianRadius = 0,
    [switch]$DisableSrgbNormalization,
    [bool]$DryRun = $true,
    [switch]$ConfirmAuthorization,
    [switch]$ConfirmWrite,
    [switch]$ConfirmExport
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Resolve-SandboxDir {
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

function Test-Settings {
    if ($ReferenceId -notmatch '^[a-z0-9][a-z0-9_-]{0,63}$') {
        throw "ReferenceId must use lowercase letters, digits, underscore, or hyphen."
    }
    if ($MaxDimension -lt 256 -or $MaxDimension -gt 8192) {
        throw "MaxDimension must be between 256 and 8192."
    }
    if ($MedianRadius -lt 0 -or $MedianRadius -gt 5) {
        throw "MedianRadius must be between 0 and 5."
    }
}

if ($ConfirmAuthorization -or $ConfirmWrite -or $ConfirmExport) {
    $DryRun = $false
}

Test-Settings
$repoRoot = Get-RepoRoot
$outDir = Resolve-SandboxDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$preparedPath = Join-Path $outDir ($ReferenceId + "_vector_source.png")
$jsxPath = Join-Path $repoRoot "examples\photoshop_bridge\jsx\color_vector_preprocess.jsx"

$plan = @{
    ok = $true
    bridge = "photoshop"
    action = "color_preprocess"
    verdict = "planned"
    reference_id = $ReferenceId
    reference_authorized = [bool]$ConfirmAuthorization
    dry_run = [bool]$DryRun
    confirm_write = [bool]$ConfirmWrite
    confirm_export = [bool]$ConfirmExport
    settings = @{
        normalize_srgb = -not [bool]$DisableSrgbNormalization
        max_dimension = $MaxDimension
        median_radius = $MedianRadius
        output_bit_depth = 8
        preserve_alpha = $true
        no_upscale = $true
    }
    outputs = @{
        prepared_png = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $preparedPath
    }
    safety = @{
        input_policy = "single_explicit_user_file"
        sandbox_copy_before_photoshop = $true
        original_modified = $false
        recursive_scan = $false
        cloud_upload = $false
        arbitrary_script = $false
    }
    warnings = @()
    next_steps = @("Review the plan, then provide one explicit PNG/JPEG and all three confirmations.")
}

if (-not $ConfirmAuthorization) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Refusing image preprocessing without explicit reference authorization.")
    Write-JsonResult $plan
    exit 0
}

if ($DryRun) {
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmWrite) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Refusing sandbox source copy without confirm_write=true.")
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmExport) {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Refusing prepared PNG export without confirm_export=true.")
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

$sourceCopyPath = Join-Path $outDir ($ReferenceId + "_source" + $extension)

try {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    Copy-Item -LiteralPath $inputFile -Destination $sourceCopyPath -Force
    $inputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $inputFile).Hash.ToLowerInvariant()
    $copyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceCopyPath).Hash.ToLowerInvariant()
    if ($inputHash -ne $copyHash) {
        throw "Sandbox copy hash mismatch."
    }

    $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Photoshop.Application")
    $config = @{
        referenceId = $ReferenceId
        inputPath = $sourceCopyPath
        outputPath = $preparedPath
        sourceCopyRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $sourceCopyPath
        outputPathRelative = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $preparedPath
        normalizeSrgb = -not [bool]$DisableSrgbNormalization
        maxDimension = $MaxDimension
        medianRadius = $MedianRadius
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -Encoding UTF8 -LiteralPath $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $payload = $raw | ConvertFrom-Json

    if (-not $payload.ok -or -not (Test-Path -LiteralPath $preparedPath -PathType Leaf)) {
        $payload | ConvertTo-Json -Depth 16
        exit 0
    }

    $outputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $preparedPath).Hash.ToLowerInvariant()
    $payload | Add-Member -NotePropertyName input_sha256 -NotePropertyValue $inputHash
    $payload | Add-Member -NotePropertyName source_copy_sha256 -NotePropertyValue $copyHash
    $payload | Add-Member -NotePropertyName output_sha256 -NotePropertyValue $outputHash
    $payload | Add-Member -NotePropertyName confirm_write -NotePropertyValue $true
    $payload | Add-Member -NotePropertyName confirm_export -NotePropertyValue $true
    $payload | Add-Member -NotePropertyName safety -NotePropertyValue ([pscustomobject]@{
        source_copy_verified = $true
        original_modified = $false
        output_sandboxed = $true
        arbitrary_script = $false
        paths_returned = $false
    })
    $payload | ConvertTo-Json -Depth 16
} catch {
    $plan.ok = $false
    $plan.verdict = "blocked"
    $plan.warnings = @("Could not run guarded color preprocessing in the active Photoshop session.")
    $plan.error_type = $_.Exception.GetType().Name
    $plan.next_steps = @(
        "Start an authorized Photoshop desktop session.",
        "Keep the explicit input unchanged and all outputs inside examples/output/photoshop.",
        "Run the dry-run plan again before retrying."
    )
    Write-JsonResult $plan
    exit 0
}
