param(
    [int]$Width = 1080,
    [int]$Height = 1080,
    [string]$OutputDir = "examples/output/illustrator",
    [bool]$DryRun = $true,
    [switch]$ConfirmWrite
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

if ($ConfirmWrite) {
    $DryRun = $false
}

$repoRoot = Get-RepoRoot
$outDir = Get-SandboxDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$outputAi = Join-Path $outDir "starbridge_ai_demo.ai"
$relativeAi = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $outputAi
$jsxPath = Join-Path $repoRoot "examples\illustrator_bridge\jsx\create_demo_artboard.jsx"

$plan = @{
    ok = $true
    bridge = "illustrator"
    task = "create_demo_artboard"
    dry_run = [bool]$DryRun
    confirm_write = [bool]$ConfirmWrite
    document = @{
        name = "starbridge_ai_demo.ai"
        width = $Width
        height = $Height
        color_space = "RGB"
    }
    artboards = @(@{ index = 0; width = $Width; height = $Height })
    layers = @("background", "foreground")
    objects_created = @("background rectangle", "title text", "subtitle text", "circle", "rectangle", "line", "path")
    output_ai_path = $relativeAi
    warnings = @()
    next_steps = @("Run with -ConfirmWrite to create the sandbox Illustrator demo document.")
}

if ($DryRun) {
    Write-JsonResult $plan
    exit 0
}

if (-not $ConfirmWrite) {
    $plan.ok = $false
    $plan.warnings = @("Refusing real Illustrator write without confirm_write=true.")
    $plan.next_steps = @("Run npm.cmd run illustrator:demo:plan first, then use -ConfirmWrite for sandbox output.")
    Write-JsonResult $plan
    exit 0
}

try {
    $app = New-Object -ComObject Illustrator.Application
    $config = @{
        width = $Width
        height = $Height
        outputAiPath = $outputAi
        outputAiPathRelative = $relativeAi
    } | ConvertTo-Json -Compress
    $jsx = "var STARBRIDGE_CONFIG = $config;`n" + (Get-Content -Raw -Path $jsxPath)
    $raw = $app.DoJavaScript($jsx)
    $raw | ConvertFrom-Json | ConvertTo-Json -Depth 12
} catch {
    $plan.ok = $false
    $plan.warnings = @("Could not create the Illustrator demo document through COM.")
    $plan.next_steps = @(
        "Start an authorized Illustrator desktop session.",
        "Verify Illustrator.Application COM is available.",
        "Run npm.cmd run illustrator:demo:plan to inspect the dry-run plan."
    )
    $plan.error_type = $_.Exception.GetType().Name
    Write-JsonResult $plan
    exit 0
}
