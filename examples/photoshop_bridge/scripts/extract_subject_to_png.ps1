param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputPath)) {
    throw "Input image not found. Pass -InputPath with a valid image path."
}

$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$OutputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Convert-ToJsString {
    param([string]$Value)
    return ($Value | ConvertTo-Json -Compress)
}

$inputJs = Convert-ToJsString ((Resolve-Path -LiteralPath $InputPath).Path -replace "\\", "/")
$outputJs = Convert-ToJsString ($OutputPath -replace "\\", "/")

$script = @"
app.displayDialogs = DialogModes.NO;

function hasSelection() {
    try {
        var bounds = app.activeDocument.selection.bounds;
        return bounds && bounds.length === 4;
    } catch (error) {
        return false;
    }
}

function selectSubject() {
    var errors = [];

    try {
        var cutoutDesc = new ActionDescriptor();
        cutoutDesc.putBoolean(stringIDToTypeID("sampleAllLayers"), false);
        executeAction(stringIDToTypeID("autoCutout"), cutoutDesc, DialogModes.NO);
        if (hasSelection()) {
            return "autoCutout";
        }
    } catch (error1) {
        errors.push("autoCutout: " + error1.message);
    }

    try {
        executeAction(stringIDToTypeID("selectSubject"), new ActionDescriptor(), DialogModes.NO);
        if (hasSelection()) {
            return "selectSubject";
        }
    } catch (error2) {
        errors.push("selectSubject: " + error2.message);
    }

    throw new Error("Photoshop Select Subject failed. " + errors.join(" | "));
}

var inputFile = new File($inputJs);
var outputFile = new File($outputJs);

if (!inputFile.exists) {
    throw new Error("Input file does not exist: " + inputFile.fsName);
}

var sourceDoc = app.open(inputFile);
app.activeDocument = sourceDoc;

var method = selectSubject();
executeAction(charIDToTypeID("CpTL"), new ActionDescriptor(), DialogModes.NO);

var subjectLayer = sourceDoc.activeLayer;
subjectLayer.name = "Codex subject cutout";

for (var i = 0; i < sourceDoc.layers.length; i++) {
    if (sourceDoc.layers[i] != subjectLayer) {
        sourceDoc.layers[i].visible = false;
    }
}

sourceDoc.trim(TrimType.TRANSPARENT, true, true, true, true);

var options = new PNGSaveOptions();
sourceDoc.saveAs(outputFile, options, true, Extension.LOWERCASE);

var result = "ok=true" +
    ";method=" + method +
    ";output=" + outputFile.fsName +
    ";width=" + sourceDoc.width +
    ";height=" + sourceDoc.height +
    ";layers=" + sourceDoc.artLayers.length;

sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
result;
"@

$app = New-Object -ComObject Photoshop.Application
$raw = $app.DoJavaScript($script)

$fields = @{}
foreach ($part in ($raw -split ";")) {
    $pair = $part -split "=", 2
    if ($pair.Count -eq 2) {
        $fields[$pair[0]] = $pair[1]
    }
}

[pscustomobject]@{
    ok = $fields["ok"] -eq "true"
    method = $fields["method"]
    output = [System.IO.Path]::GetFileName($OutputPath)
    output_dir = "local output directory"
    width = $fields["width"]
    height = $fields["height"]
    layers = $fields["layers"]
    exists = (Test-Path -LiteralPath $OutputPath)
} | ConvertTo-Json -Depth 6
