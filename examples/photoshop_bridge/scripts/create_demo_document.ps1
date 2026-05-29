param(
    [int]$Width = 1080,
    [int]$Height = 1080,
    [int]$Dpi = 72,
    [string]$OutputDir = "examples/output/photoshop",
    [bool]$DryRun = $true,
    [switch]$ConfirmWrite
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

if ($ConfirmWrite) {
    $DryRun = $false
}

$repoRoot = Get-RepoRoot
$outDir = Get-SandboxDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$outputPsd = Join-Path $outDir "starbridge_ps_demo.psd"
$relativePsd = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $outputPsd
$jsxPath = Join-Path $repoRoot "examples\photoshop_bridge\jsx\create_demo_document.jsx"

$plan = @{
    ok = $true
    bridge = "photoshop"
    task = "create_demo_document"
    dry_run = [bool]$DryRun
    confirm_write = [bool]$ConfirmWrite
    document = @{
        name = "starbridge_ps_demo.psd"
        width = $Width
        height = $Height
        dpi = $Dpi
        color_mode = "RGB"
    }
    layers_created = @("background", "color_block_left", "color_block_right", "title_text", "subtitle_text")
    output_psd_path = $relativePsd
    warnings = @()
    next_steps = @("Run with -ConfirmWrite to create the sandbox Photoshop demo PSD.")
}

if ($DryRun) {
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmWrite) {
    $plan.ok = $false
    $plan.warnings = @("Refusing real Photoshop write without confirm_write=true.")
    $plan.next_steps = @("Run npm.cmd run photoshop:demo:plan first, then use -ConfirmWrite for sandbox output.")
    Write-JsonResult $plan
    exit 0
}

try {
    $app = New-Object -ComObject Photoshop.Application
    $config = @{
        width = $Width
        height = $Height
        dpi = $Dpi
        outputPsdPath = $outputPsd
        outputPsdPathRelative = $relativePsd
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -Path $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $raw | ConvertFrom-Json | ConvertTo-Json -Depth 12
} catch {
    $plan.ok = $false
    $plan.warnings = @("Could not create the Photoshop demo document through COM.")
    $plan.next_steps = @(
        "Start an authorized Photoshop desktop session.",
        "Verify Photoshop.Application COM is available.",
        "Run npm.cmd run photoshop:demo:plan to inspect the dry-run plan."
    )
    $plan.error_type = $_.Exception.GetType().Name
    Write-JsonResult $plan
    exit 0
}
