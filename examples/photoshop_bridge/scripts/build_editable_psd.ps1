param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [switch]$ConfirmWrite,
    [switch]$OpenAfterBuild
)

$ErrorActionPreference = "Stop"

function Test-IsInside {
    param([string]$Candidate, [string]$Root)
    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate)
    $fullRoot = [System.IO.Path]::GetFullPath($Root)
    $separator = [System.IO.Path]::DirectorySeparatorChar
    return $fullCandidate -eq $fullRoot -or $fullCandidate.StartsWith(
        $fullRoot + $separator,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Write-Result {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 16
}

if (-not $ConfirmWrite) {
    Write-Result @{
        ok = $false
        task = "build_editable_psd"
        message = "Refusing Photoshop write without -ConfirmWrite."
        confirmation_required = $true
    }
    exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "examples\output\photoshop"))
$manifestFull = [System.IO.Path]::GetFullPath($ManifestPath)
$outputFull = [System.IO.Path]::GetFullPath($OutputPath)

if (-not (Test-IsInside -Candidate $manifestFull -Root $allowedRoot)) {
    throw "ManifestPath must stay inside examples/output/photoshop."
}
if (-not (Test-IsInside -Candidate $outputFull -Root $allowedRoot)) {
    throw "OutputPath must stay inside examples/output/photoshop."
}
if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) {
    throw "Manifest file does not exist."
}
if ([System.IO.Path]::GetExtension($outputFull).ToLowerInvariant() -ne ".psd") {
    throw "OutputPath must end with .psd."
}

$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestFull | ConvertFrom-Json
if ($manifest.schema_version -ne "starbridge.image_to_editable_psd.v1") {
    throw "Unsupported manifest schema_version."
}

$manifestDir = Split-Path -Parent $manifestFull
$groups = @($manifest.groups_bottom_to_top)
$layers = @($manifest.layers | Sort-Object -Property z_index)
$layerSpecs = @()
foreach ($layer in $layers) {
    $spec = [ordered]@{
        id = [string]$layer.id
        name = [string]$layer.name
        group = [string]$layer.group
        type = [string]$layer.type
        visible = [bool]$layer.visible
        locked = [bool]$layer.locked
        z_index = [int]$layer.z_index
    }
    if ($layer.type -eq "pixel") {
        $sourceFull = [System.IO.Path]::GetFullPath((Join-Path $manifestDir $layer.source))
        if (-not (Test-IsInside -Candidate $sourceFull -Root $manifestDir)) {
            throw "A layer source escaped the manifest job directory."
        }
        if (-not (Test-Path -LiteralPath $sourceFull -PathType Leaf)) {
            throw "A layer source file is missing: $($layer.source)"
        }
        $spec.source = ($sourceFull -replace "\\", "/")
    } else {
        $spec.content = [string]$layer.content
        $spec.position = @([double]$layer.position[0], [double]$layer.position[1])
        $spec.font_size = [double]$layer.font_size
        $spec.font_candidates = @($layer.font_candidates)
        $spec.color = [string]$layer.color
    }
    $layerSpecs += [pscustomobject]$spec
}

$hiddenGroups = @()
foreach ($groupName in $groups) {
    $members = @($layerSpecs | Where-Object { $_.group -eq $groupName })
    $visibleMembers = @($members | Where-Object { $_.visible })
    if ($members.Count -gt 0 -and $visibleMembers.Count -eq 0) {
        $hiddenGroups += [string]$groupName
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputFull) | Out-Null
$config = [ordered]@{
    width = [int]$manifest.canvas.width
    height = [int]$manifest.canvas.height
    resolution = [int]$manifest.canvas.resolution
    output = ($outputFull -replace "\\", "/")
    groups = $groups
    hidden_groups = $hiddenGroups
    layers = $layerSpecs
    open_after_build = [bool]$OpenAfterBuild
} | ConvertTo-Json -Depth 20 -Compress

$jsx = @"
app.displayDialogs = DialogModes.NO;
var CONFIG = $config;

function colorFromHex(value) {
    var text = String(value || "#FFFFFF").replace("#", "");
    if (text.length !== 6) text = "FFFFFF";
    var color = new SolidColor();
    color.rgb.red = parseInt(text.substring(0, 2), 16);
    color.rgb.green = parseInt(text.substring(2, 4), 16);
    color.rgb.blue = parseInt(text.substring(4, 6), 16);
    return color;
}

function importPixelLayer(doc, groups, spec) {
    var file = new File(spec.source);
    if (!file.exists) throw new Error("Layer source is missing: " + spec.id);
    var sourceDoc = app.open(file);
    app.activeDocument = sourceDoc;
    try {
        if (sourceDoc.mode !== DocumentMode.RGB) sourceDoc.changeMode(ChangeMode.RGB);
    } catch (ignoredMode) {}
    var duplicated = sourceDoc.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
    sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;
    duplicated.name = spec.name;
    duplicated.move(groups[spec.group], ElementPlacement.PLACEATBEGINNING);
    duplicated.visible = spec.visible;
    try { duplicated.allLocked = spec.locked; } catch (ignoredLock) {}
    return duplicated;
}

function createTextLayer(doc, groups, spec) {
    var layer = doc.artLayers.add();
    layer.kind = LayerKind.TEXT;
    layer.name = spec.name;
    layer.textItem.contents = spec.content;
    layer.textItem.position = [UnitValue(spec.position[0], "px"), UnitValue(spec.position[1], "px")];
    layer.textItem.size = UnitValue(Math.max(6, spec.font_size), "pt");
    layer.textItem.color = colorFromHex(spec.color);
    if (spec.font_candidates && spec.font_candidates.length) {
        for (var i = 0; i < spec.font_candidates.length; i++) {
            try {
                layer.textItem.font = spec.font_candidates[i];
                break;
            } catch (ignoredFont) {}
        }
    }
    layer.move(groups[spec.group], ElementPlacement.PLACEATBEGINNING);
    layer.visible = spec.visible;
    try { layer.allLocked = spec.locked; } catch (ignoredLock) {}
    return layer;
}

function arrayContains(values, expected) {
    for (var index = 0; index < values.length; index++) {
        if (values[index] === expected) return true;
    }
    return false;
}

function findTopLevelGroup(doc, name) {
    for (var index = 0; index < doc.layerSets.length; index++) {
        if (doc.layerSets[index].name === name) return doc.layerSets[index];
    }
    return null;
}

function findDirectArtLayer(group, name) {
    for (var index = 0; index < group.artLayers.length; index++) {
        if (group.artLayers[index].name === name) return group.artLayers[index];
    }
    return null;
}

function validatePersistedDocument(doc) {
    var missingGroups = 0;
    var missingLayers = 0;
    var groupVisibilityMismatches = 0;
    var layerVisibilityMismatches = 0;
    var lockMismatches = 0;
    var typeMismatches = 0;
    var emptyPixelLayers = 0;
    var actualLayerCount = 0;

    for (var groupIndex = 0; groupIndex < CONFIG.groups.length; groupIndex++) {
        var groupName = CONFIG.groups[groupIndex];
        var group = findTopLevelGroup(doc, groupName);
        if (!group) {
            missingGroups++;
            continue;
        }
        actualLayerCount += group.artLayers.length;
        var expectedGroupVisible = !arrayContains(CONFIG.hidden_groups, groupName);
        if (Boolean(group.visible) !== expectedGroupVisible) groupVisibilityMismatches++;
    }

    for (var layerIndex = 0; layerIndex < CONFIG.layers.length; layerIndex++) {
        var spec = CONFIG.layers[layerIndex];
        var parent = findTopLevelGroup(doc, spec.group);
        var layer = parent ? findDirectArtLayer(parent, spec.name) : null;
        if (!layer) {
            missingLayers++;
            continue;
        }
        if (Boolean(layer.visible) !== Boolean(spec.visible)) layerVisibilityMismatches++;
        try {
            if (Boolean(layer.allLocked) !== Boolean(spec.locked)) lockMismatches++;
        } catch (ignoredLockRead) {
            lockMismatches++;
        }
        if (spec.type === "text" && layer.kind !== LayerKind.TEXT) typeMismatches++;
        if (spec.type === "pixel") {
            if (layer.kind === LayerKind.TEXT) typeMismatches++;
            try {
                var bounds = layer.bounds;
                var width = Number(bounds[2].as("px")) - Number(bounds[0].as("px"));
                var height = Number(bounds[3].as("px")) - Number(bounds[1].as("px"));
                if (!(width > 0 && height > 0)) emptyPixelLayers++;
            } catch (ignoredBounds) {
                emptyPixelLayers++;
            }
        }
    }

    var dimensionsMatch = Math.round(Number(doc.width.as("px"))) === CONFIG.width &&
        Math.round(Number(doc.height.as("px"))) === CONFIG.height;
    var structureOk = dimensionsMatch &&
        doc.layerSets.length === CONFIG.groups.length &&
        actualLayerCount === CONFIG.layers.length &&
        missingGroups === 0 &&
        missingLayers === 0 &&
        groupVisibilityMismatches === 0 &&
        layerVisibilityMismatches === 0 &&
        lockMismatches === 0 &&
        typeMismatches === 0 &&
        emptyPixelLayers === 0;
    return {
        ok: structureOk,
        dimensions_match: dimensionsMatch,
        actual_group_count: doc.layerSets.length,
        actual_layer_count: actualLayerCount,
        missing_group_count: missingGroups,
        missing_layer_count: missingLayers,
        group_visibility_mismatch_count: groupVisibilityMismatches,
        layer_visibility_mismatch_count: layerVisibilityMismatches,
        lock_mismatch_count: lockMismatches,
        type_mismatch_count: typeMismatches,
        empty_pixel_layer_count: emptyPixelLayers
    };
}

var previousUnits = app.preferences.rulerUnits;
app.preferences.rulerUnits = Units.PIXELS;
var doc = app.documents.add(
    CONFIG.width,
    CONFIG.height,
    CONFIG.resolution,
    "StarBridge_Editable_PSD",
    NewDocumentMode.RGB,
    DocumentFill.TRANSPARENT
);
var initialLayer = doc.activeLayer;
var groups = {};
for (var groupIndex = 0; groupIndex < CONFIG.groups.length; groupIndex++) {
    var group = doc.layerSets.add();
    group.name = CONFIG.groups[groupIndex];
    groups[group.name] = group;
}
for (var layerIndex = 0; layerIndex < CONFIG.layers.length; layerIndex++) {
    var spec = CONFIG.layers[layerIndex];
    if (!groups[spec.group]) throw new Error("Unknown group: " + spec.group);
    if (spec.type === "pixel") importPixelLayer(doc, groups, spec);
    else if (spec.type === "text") createTextLayer(doc, groups, spec);
    else throw new Error("Unsupported layer type: " + spec.type);
}
try { initialLayer.remove(); } catch (ignoredInitial) {}
for (var hiddenIndex = 0; hiddenIndex < CONFIG.hidden_groups.length; hiddenIndex++) {
    var hiddenName = CONFIG.hidden_groups[hiddenIndex];
    if (groups[hiddenName]) groups[hiddenName].visible = false;
}

var outputFile = new File(CONFIG.output);
if (outputFile.exists) outputFile.remove();
var saveOptions = new PhotoshopSaveOptions();
saveOptions.layers = true;
saveOptions.alphaChannels = true;
doc.saveAs(outputFile, saveOptions, false, Extension.LOWERCASE);
app.preferences.rulerUnits = previousUnits;
doc.close(SaveOptions.DONOTSAVECHANGES);

var persistedDoc = app.open(outputFile);
var validation = validatePersistedDocument(persistedDoc);
if (!CONFIG.open_after_build) persistedDoc.close(SaveOptions.DONOTSAVECHANGES);
"ok=" + (outputFile.exists && validation.ok) +
    ";bridge=photoshop_com_jsx" +
    ";task=build_editable_psd" +
    ";output=" + outputFile.name +
    ";width=" + CONFIG.width +
    ";height=" + CONFIG.height +
    ";layer_count=" + CONFIG.layers.length +
    ";group_count=" + CONFIG.groups.length +
    ";kept_open=" + CONFIG.open_after_build +
    ";validated_after_reopen=true" +
    ";dimensions_match=" + validation.dimensions_match +
    ";actual_group_count=" + validation.actual_group_count +
    ";actual_layer_count=" + validation.actual_layer_count +
    ";missing_group_count=" + validation.missing_group_count +
    ";missing_layer_count=" + validation.missing_layer_count +
    ";group_visibility_mismatch_count=" + validation.group_visibility_mismatch_count +
    ";layer_visibility_mismatch_count=" + validation.layer_visibility_mismatch_count +
    ";lock_mismatch_count=" + validation.lock_mismatch_count +
    ";type_mismatch_count=" + validation.type_mismatch_count +
    ";empty_pixel_layer_count=" + validation.empty_pixel_layer_count;
"@

try {
    $app = New-Object -ComObject Photoshop.Application
    $raw = $app.DoJavaScript($jsx)
    $result = @{}
    foreach ($part in ($raw -split ";")) {
        $pair = $part -split "=", 2
        if ($pair.Count -eq 2) {
            $result[$pair[0]] = $pair[1]
        }
    }
    Write-Result @{
        ok = $result["ok"] -eq "true"
        bridge = [string]$result["bridge"]
        task = [string]$result["task"]
        output = [string]$result["output"]
        output_dir = "examples/output/photoshop"
        width = [int]$result["width"]
        height = [int]$result["height"]
        layer_count = [int]$result["layer_count"]
        group_count = [int]$result["group_count"]
        kept_open = $result["kept_open"] -eq "true"
        validated_after_reopen = $result["validated_after_reopen"] -eq "true"
        dimensions_match = $result["dimensions_match"] -eq "true"
        actual_group_count = [int]$result["actual_group_count"]
        actual_layer_count = [int]$result["actual_layer_count"]
        missing_group_count = [int]$result["missing_group_count"]
        missing_layer_count = [int]$result["missing_layer_count"]
        group_visibility_mismatch_count = [int]$result["group_visibility_mismatch_count"]
        layer_visibility_mismatch_count = [int]$result["layer_visibility_mismatch_count"]
        lock_mismatch_count = [int]$result["lock_mismatch_count"]
        type_mismatch_count = [int]$result["type_mismatch_count"]
        empty_pixel_layer_count = [int]$result["empty_pixel_layer_count"]
        private_paths_recorded = $false
    }
} catch {
    $safeMessage = [string]$_.Exception.Message
    $safeMessage = $safeMessage -replace [regex]::Escape($repoRoot), "<REPO_ROOT>"
    $safeMessage = $safeMessage -replace [regex]::Escape($manifestDir), "<JOB_DIR>"
    Write-Result @{
        ok = $false
        bridge = "photoshop_com_jsx"
        task = "build_editable_psd"
        message = "Photoshop could not build the editable PSD."
        error_type = $_.Exception.GetType().Name
        error_detail = $safeMessage
        error_code = $_.Exception.HResult
        private_paths_recorded = $false
    }
}
