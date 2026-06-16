param(
    [Parameter(Mandatory=$true)]
    [string]$InputPath,
    [string]$OutputDir = "examples/output/photoshop",
    [string]$Basename = "camera_raw_tuned",
    [double]$Exposure = 0.0,
    [double]$Contrast = 0.0,
    [double]$Highlights = 0.0,
    [double]$Shadows = 0.0,
    [double]$Whites = 0.0,
    [double]$Blacks = 0.0,
    [double]$Texture = 0.0,
    [double]$Vibrance = 0.0,
    [switch]$ConfirmApply,
    [switch]$ConfirmExport
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-SafeOutputDir {
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

function Format-XmpNumber {
    param([double]$Value)
    if ([Math]::Abs($Value - [Math]::Round($Value)) -lt 0.000001) {
        return ([int][Math]::Round($Value)).ToString([Globalization.CultureInfo]::InvariantCulture)
    }
    return $Value.ToString("0.####", [Globalization.CultureInfo]::InvariantCulture)
}

function Write-CameraRawXmp {
    param(
        [string]$Path,
        [hashtable]$Settings
    )
    $lines = @()
    foreach ($key in ($Settings.Keys | Sort-Object)) {
        $lines += "   crs:$key=`"$($Settings[$key])`""
    }
    $attributes = $lines -join "`n"
    $xmp = @"
<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
$attributes/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"@
    Set-Content -LiteralPath $Path -Value $xmp -Encoding UTF8
}

function Write-JsonResult {
    param([hashtable]$Result)
    $Result | ConvertTo-Json -Depth 12
}

if (-not $ConfirmApply -or -not $ConfirmExport) {
    Write-JsonResult @{
        ok = $false
        bridge = "photoshop"
        task = "camera_raw_export"
        dry_run = $true
        confirm_apply = [bool]$ConfirmApply
        confirm_export = [bool]$ConfirmExport
        warnings = @("Real Camera Raw export requires -ConfirmApply and -ConfirmExport.")
        next_steps = @("Run the dry-run plan first, then retry with both confirmation flags for sandbox output.")
    }
    exit 0
}

$repoRoot = Get-RepoRoot
$outDir = Get-SafeOutputDir -RepoRoot $repoRoot -RequestedDir $OutputDir
$inputFull = [System.IO.Path]::GetFullPath($InputPath)
if (-not (Test-Path -LiteralPath $inputFull)) {
    throw "InputPath does not exist."
}

$safeRawPath = Join-Path $outDir ($Basename + [System.IO.Path]::GetExtension($inputFull))
$safeXmpPath = Join-Path $outDir ($Basename + ".xmp")
$jpgPath = Join-Path $outDir ($Basename + ".jpg")
$jsxPath = Join-Path $outDir ($Basename + ".camera_raw_export.jsx")

Copy-Item -LiteralPath $inputFull -Destination $safeRawPath -Force

$settings = @{
    Exposure2012 = Format-XmpNumber $Exposure
    Contrast2012 = Format-XmpNumber $Contrast
    Highlights2012 = Format-XmpNumber $Highlights
    Shadows2012 = Format-XmpNumber $Shadows
    Whites2012 = Format-XmpNumber $Whites
    Blacks2012 = Format-XmpNumber $Blacks
    Texture = Format-XmpNumber $Texture
    Vibrance = Format-XmpNumber $Vibrance
}
Write-CameraRawXmp -Path $safeXmpPath -Settings $settings

$config = @{
    rawPath = $safeRawPath
    jpgPath = $jpgPath
} | ConvertTo-Json -Compress

$jsx = @"
var STARBRIDGE_CONFIG = $config;
var result = { ok: false, warnings: [], exported_files: [] };
function quoteJson(value) {
    return '"' + String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r/g, "\\r").replace(/\n/g, "\\n") + '"';
}
function resultJson(ok, path, warning, error) {
    var text = '{"ok":' + (ok ? 'true' : 'false');
    if (path) text += ',"exported_files":[' + quoteJson(path) + ']';
    if (warning) text += ',"warnings":[' + quoteJson(warning) + ']';
    if (error) text += ',"error":' + quoteJson(error);
    return text + '}';
}
try {
    app.displayDialogs = DialogModes.NO;
    var rawFile = new File(STARBRIDGE_CONFIG.rawPath);
    var jpgFile = new File(STARBRIDGE_CONFIG.jpgPath);
    var doc = app.open(rawFile);
    var opts = new JPEGSaveOptions();
    opts.quality = 12;
    opts.embedColorProfile = true;
    opts.formatOptions = FormatOptions.STANDARDBASELINE;
    doc.saveAs(jpgFile, opts, true, Extension.LOWERCASE);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    result.ok = true;
    result.exported_files = [STARBRIDGE_CONFIG.jpgPath];
    resultJson(true, STARBRIDGE_CONFIG.jpgPath, "", "");
} catch (e) {
    resultJson(false, "", "Photoshop Camera Raw export failed.", String(e));
}
"@
Set-Content -LiteralPath $jsxPath -Value $jsx -Encoding UTF8

try {
    $app = New-Object -ComObject Photoshop.Application
    $raw = $app.DoJavaScript((Get-Content -Raw -LiteralPath $jsxPath))
    $payload = $raw | ConvertFrom-Json
    if ($payload.ok -and (Test-Path -LiteralPath $jpgPath)) {
        Write-JsonResult @{
            ok = $true
            bridge = "photoshop"
            task = "camera_raw_export"
            confirm_apply = $true
            confirm_export = $true
            input_copy = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeRawPath
            xmp_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeXmpPath
            jpg_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jpgPath
            jsx_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jsxPath
            warnings = @()
        }
        exit 0
    }
    Write-JsonResult @{
        ok = $false
        bridge = "photoshop"
        task = "camera_raw_export"
        input_copy = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeRawPath
        xmp_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeXmpPath
        jsx_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jsxPath
        warnings = @("Photoshop did not produce the expected JPG.")
        photoshop_result = $payload
    }
    exit 0
} catch {
    Write-JsonResult @{
        ok = $false
        bridge = "photoshop"
        task = "camera_raw_export"
        input_copy = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeRawPath
        xmp_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $safeXmpPath
        jsx_path = Convert-ToRepoRelative -RepoRoot $repoRoot -PathValue $jsxPath
        error_type = $_.Exception.GetType().Name
        error_message = $_.Exception.Message
        warnings = @("Could not run Photoshop Camera Raw export through COM.")
    }
    exit 0
}
