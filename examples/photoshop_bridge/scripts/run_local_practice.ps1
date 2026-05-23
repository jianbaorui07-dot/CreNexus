param(
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "output\photoshop_bridge_practice"
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$probeOutput = Join-Path $OutputDir "codex_photoshop_probe.png"
$subjectInput = Join-Path $OutputDir "subject_input_clean.png"
$subjectOutput = Join-Path $OutputDir "subject_cutout_clean.png"

foreach ($artifactPath in @($probeOutput, $subjectInput, $subjectOutput)) {
    if (Test-Path -LiteralPath $artifactPath) {
        Remove-Item -LiteralPath $artifactPath -Force
    }
}

function Test-RetryablePhotoshopError {
    param([string]$Message)

    return $Message -match "RPC_E_SERVERCALL_RETRYLATER|application is busy|message filter"
}

function Invoke-JsonStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $true)]
        [hashtable]$Parameters,

        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    $attempts = 3
    for ($attempt = 1; $attempt -le $attempts; $attempt++) {
        try {
            $raw = & $ScriptPath @Parameters
            $payload = $raw | ConvertFrom-Json
            $payload | Add-Member -NotePropertyName retry_attempt -NotePropertyValue $attempt -Force
            return $payload
        } catch {
            $message = $_.Exception.Message
            if ($attempt -ge $attempts -or -not (Test-RetryablePhotoshopError -Message $message)) {
                throw "$StepName failed after $attempt attempt(s): $message"
            }
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
}

function New-PublicSubjectImage {
    param([string]$Path)

    Add-Type -AssemblyName System.Drawing
    $bitmap = New-Object System.Drawing.Bitmap 900, 600
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::White)

    $shadowBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(55, 0, 0, 0))
    $subjectBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 40, 120, 210))
    $accentBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 235, 80, 70))

    $graphics.FillEllipse($shadowBrush, 285, 485, 330, 55)
    $graphics.FillEllipse($subjectBrush, 300, 80, 300, 420)
    $graphics.FillRectangle($accentBrush, 410, 235, 80, 180)
    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)

    $graphics.Dispose()
    $bitmap.Dispose()
    $shadowBrush.Dispose()
    $subjectBrush.Dispose()
    $accentBrush.Dispose()
}

$probe = Invoke-JsonStep `
    -ScriptPath (Join-Path $PSScriptRoot "com_probe.ps1") `
    -Parameters @{ OutputPath = $probeOutput } `
    -StepName "Photoshop COM probe"
New-PublicSubjectImage -Path $subjectInput
$cutout = Invoke-JsonStep `
    -ScriptPath (Join-Path $PSScriptRoot "extract_subject_to_png.ps1") `
    -Parameters @{ InputPath = $subjectInput; OutputPath = $subjectOutput } `
    -StepName "Photoshop subject cutout"

[pscustomobject]@{
    ok = [bool]($probe.ok -and $cutout.ok)
    status_label = "Photoshop local bridge practice completed"
    photoshop_version = $probe.photoshopVersion
    probe_output = $probe.output
    subject_input = $subjectInput
    subject_cutout_method = $cutout.method
    subject_cutout_output = $cutout.output
    subject_cutout_exists = $cutout.exists
    probe_retry_attempt = $probe.retry_attempt
    subject_cutout_retry_attempt = $cutout.retry_attempt
    output_dir = $OutputDir
    note = "The output directory is local generated content and is ignored by the output/ rule in .gitignore."
} | ConvertTo-Json -Depth 6
