param(
    [string]$OutputPath = (Join-Path $env:TEMP "codex_photoshop_probe.png")
)

$ErrorActionPreference = "Stop"

$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$OutputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Convert-ToJsString {
    param([string]$Value)
    return ($Value | ConvertTo-Json -Compress)
}

$outputJs = Convert-ToJsString ($OutputPath -replace "\\", "/")

$script = @"
app.displayDialogs = DialogModes.NO;
var doc = app.documents.add(900, 540, 72, "Codex_Photoshop_Probe", NewDocumentMode.RGB, DocumentFill.WHITE);
var titleLayer = doc.artLayers.add();
titleLayer.kind = LayerKind.TEXT;
titleLayer.name = "Codex connection title";
titleLayer.textItem.contents = "Codex connected to Photoshop";
titleLayer.textItem.size = 36;
titleLayer.textItem.position = [70, 120];
var infoLayer = doc.artLayers.add();
infoLayer.kind = LayerKind.TEXT;
infoLayer.name = "Codex connection info";
infoLayer.textItem.contents = "COM + JavaScript probe OK\nVersion: " + app.version;
infoLayer.textItem.size = 22;
infoLayer.textItem.position = [70, 190];
var pngFile = new File($outputJs);
var pngOptions = new PNGSaveOptions();
doc.saveAs(pngFile, pngOptions, true, Extension.LOWERCASE);
"ok=true" +
";version=" + app.version +
";document=" + doc.name +
";width=" + doc.width +
";height=" + doc.height +
";layers=" + doc.artLayers.length +
";output=" + pngFile.fsName;
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
    photoshopVersion = $fields["version"]
    document = $fields["document"]
    width = $fields["width"]
    height = $fields["height"]
    layers = $fields["layers"]
    output = [System.IO.Path]::GetFileName($OutputPath)
    output_dir = "local output directory"
    exists = (Test-Path -LiteralPath $OutputPath)
} | ConvertTo-Json -Depth 6
