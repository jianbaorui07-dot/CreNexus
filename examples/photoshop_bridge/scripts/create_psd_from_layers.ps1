param(
    [Parameter(Mandatory = $true)]
    [string]$ReportPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ReportPath)) {
    throw "Layer report not found."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$allowed = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "examples\output\photoshop"))
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $OutputPath.StartsWith($allowed, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputPath must stay inside examples/output/photoshop."
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

$report = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReportPath | ConvertFrom-Json
$width = [int]$report.source.width
$height = [int]$report.source.height
$layers = @($report.layers)

function Convert-ToJsString {
    param([string]$Value)
    return ($Value | ConvertTo-Json -Compress)
}

$layerJson = @()
foreach ($layer in $layers) {
    $path = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $layer.file))
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Layer file missing: $($layer.file)"
    }
    $layerJson += [pscustomobject]@{
        name = $layer.name
        path = ($path -replace "\\", "/")
    }
}

$layersJs = ($layerJson | ConvertTo-Json -Compress)
$outputJs = Convert-ToJsString ($OutputPath -replace "\\", "/")

$script = @"
app.displayDialogs = DialogModes.NO;
var layerSpecs = $layersJs;
var outFile = new File($outputJs);
var doc = app.documents.add($width, $height, 72, "starbridge_subject_layers", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
var initialLayer = doc.activeLayer;

function openLayer(spec) {
    var file = new File(spec.path);
    if (!file.exists) {
        throw new Error("Layer file does not exist: " + spec.path);
    }
    var src = app.open(file);
    app.activeDocument = src;
    src.activeLayer.name = spec.name;
    src.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
    src.close(SaveOptions.DONOTSAVECHANGES);
}

for (var i = layerSpecs.length - 1; i >= 0; i--) {
    openLayer(layerSpecs[i]);
}

app.activeDocument = doc;
try {
    initialLayer.remove();
} catch (ignored) {}
var saveOptions = new PhotoshopSaveOptions();
saveOptions.layers = true;
doc.saveAs(outFile, saveOptions, true, Extension.LOWERCASE);
doc.close(SaveOptions.DONOTSAVECHANGES);

"ok=true;bridge=photoshop;task=create_psd_from_subject_layers;output=" + outFile.name + ";width=$width;height=$height;layer_count=" + layerSpecs.length;
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
    bridge = $fields["bridge"]
    task = $fields["task"]
    output = $fields["output"]
    output_dir = "local output directory"
    width = $fields["width"]
    height = $fields["height"]
    layer_count = [int]$fields["layer_count"]
    exists = Test-Path -LiteralPath $OutputPath
} | ConvertTo-Json -Depth 6
