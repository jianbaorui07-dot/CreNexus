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
        task = "build_smart_cutout_psd"
        message = "Refusing Photoshop write without -ConfirmWrite."
        confirmation_required = $true
    }
    exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
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
if (Test-Path -LiteralPath $outputFull) {
    throw "Output PSD already exists; choose a new filename."
}

$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestFull | ConvertFrom-Json
if ($manifest.schema_version -ne "starbridge.image_to_editable_psd.v1") {
    throw "Unsupported manifest schema_version."
}

$manifestDir = Split-Path -Parent $manifestFull
$allowedGroups = @(
    ("04_" + [char]0x80CC + [char]0x666F),
    ("03_" + [char]0x88C5 + [char]0x9970),
    ("02_" + [char]0x4E3B + [char]0x4F53),
    ("01_" + [char]0x6587 + [char]0x5B57),
    ("00_" + [char]0x539F + [char]0x59CB + [char]0x53C2 + [char]0x8003),
    "99_QA"
)
$layers = @($manifest.layers | Sort-Object -Property z_index)
if ($layers.Count -eq 0) {
    throw "Manifest contains no layers."
}

$layerSpecs = @()
foreach ($layer in $layers) {
    if ($layer.type -ne "pixel") {
        throw "Smart cutout manifests may contain pixel layers only."
    }
    if ($allowedGroups -notcontains [string]$layer.group) {
        throw "A layer group is not allowlisted."
    }
    $sourceFull = [System.IO.Path]::GetFullPath((Join-Path $manifestDir $layer.source))
    if (-not (Test-IsInside -Candidate $sourceFull -Root $manifestDir)) {
        throw "A layer source escaped the manifest job directory."
    }
    if (-not (Test-Path -LiteralPath $sourceFull -PathType Leaf)) {
        throw "A layer source file is missing."
    }
    $layerSpecs += [pscustomobject][ordered]@{
        id = [string]$layer.id
        name = [string]$layer.name
        group = [string]$layer.group
        source = ($sourceFull -replace "\\", "/")
        visible = [bool]$layer.visible
        locked = [bool]$layer.locked
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputFull) | Out-Null
$config = [ordered]@{
    width = [int]$manifest.canvas.width
    height = [int]$manifest.canvas.height
    resolution = [int]$manifest.canvas.resolution
    output = ($outputFull -replace "\\", "/")
    groups = $allowedGroups
    layers = $layerSpecs
    open_after_build = [bool]$OpenAfterBuild
} | ConvertTo-Json -Depth 16 -Compress

$jsx = @"
app.displayDialogs = DialogModes.NO;
var CONFIG = $config;

function importLayer(doc, groups, spec) {
    var file = new File(spec.source);
    if (!file.exists) throw new Error("Layer source is missing: " + spec.id);
    var sourceDoc = app.open(file);
    app.activeDocument = sourceDoc;
    try {
        if (sourceDoc.mode !== DocumentMode.RGB) sourceDoc.changeMode(ChangeMode.RGB);
    } catch (ignoredMode) {}
    var layer = sourceDoc.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
    sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;
    layer.name = spec.name;
    layer.move(groups[spec.group], ElementPlacement.PLACEATBEGINNING);
    layer.visible = spec.visible;
    try { layer.allLocked = spec.locked; } catch (ignoredLock) {}
}

function findGroup(doc, name) {
    for (var index = 0; index < doc.layerSets.length; index++) {
        if (doc.layerSets[index].name === name) return doc.layerSets[index];
    }
    return null;
}

function findLayer(group, name) {
    for (var index = 0; index < group.artLayers.length; index++) {
        if (group.artLayers[index].name === name) return group.artLayers[index];
    }
    return null;
}

function validateDocument(doc) {
    var missingGroups = 0;
    var missingLayers = 0;
    var visibilityMismatches = 0;
    var lockMismatches = 0;
    var emptyLayers = 0;
    var actualLayerCount = 0;
    for (var groupIndex = 0; groupIndex < CONFIG.groups.length; groupIndex++) {
        var group = findGroup(doc, CONFIG.groups[groupIndex]);
        if (!group) missingGroups++;
        else actualLayerCount += group.artLayers.length;
    }
    for (var layerIndex = 0; layerIndex < CONFIG.layers.length; layerIndex++) {
        var spec = CONFIG.layers[layerIndex];
        var parent = findGroup(doc, spec.group);
        var layer = parent ? findLayer(parent, spec.name) : null;
        if (!layer) {
            missingLayers++;
            continue;
        }
        var effectiveVisible = Boolean(layer.visible) && Boolean(parent.visible);
        if (effectiveVisible !== Boolean(spec.visible)) visibilityMismatches++;
        try {
            if (Boolean(layer.allLocked) !== Boolean(spec.locked)) lockMismatches++;
        } catch (ignoredLockRead) {
            lockMismatches++;
        }
        try {
            var bounds = layer.bounds;
            var width = Number(bounds[2].as("px")) - Number(bounds[0].as("px"));
            var height = Number(bounds[3].as("px")) - Number(bounds[1].as("px"));
            if (!(width > 0 && height > 0)) emptyLayers++;
        } catch (ignoredBounds) {
            emptyLayers++;
        }
    }
    var dimensionsMatch = Math.round(Number(doc.width.as("px"))) === CONFIG.width &&
        Math.round(Number(doc.height.as("px"))) === CONFIG.height;
    return {
        ok: dimensionsMatch &&
            doc.layerSets.length === CONFIG.groups.length &&
            actualLayerCount === CONFIG.layers.length &&
            missingGroups === 0 &&
            missingLayers === 0 &&
            visibilityMismatches === 0 &&
            lockMismatches === 0 &&
            emptyLayers === 0,
        dimensions_match: dimensionsMatch,
        actual_group_count: doc.layerSets.length,
        actual_layer_count: actualLayerCount,
        missing_group_count: missingGroups,
        missing_layer_count: missingLayers,
        visibility_mismatch_count: visibilityMismatches,
        lock_mismatch_count: lockMismatches,
        empty_layer_count: emptyLayers
    };
}

var previousUnits = app.preferences.rulerUnits;
app.preferences.rulerUnits = Units.PIXELS;
var doc = app.documents.add(
    CONFIG.width,
    CONFIG.height,
    CONFIG.resolution,
    "StarBridge_Smart_Cutout",
    NewDocumentMode.RGB,
    DocumentFill.TRANSPARENT
);
var placeholder = doc.activeLayer;
var groups = {};
for (var groupIndex = 0; groupIndex < CONFIG.groups.length; groupIndex++) {
    var group = doc.layerSets.add();
    group.name = CONFIG.groups[groupIndex];
    groups[group.name] = group;
}
for (var layerIndex = 0; layerIndex < CONFIG.layers.length; layerIndex++) {
    importLayer(doc, groups, CONFIG.layers[layerIndex]);
}
try { placeholder.remove(); } catch (ignoredPlaceholder) {}
for (var visibilityGroupIndex = 0; visibilityGroupIndex < CONFIG.groups.length; visibilityGroupIndex++) {
    var visibilityGroupName = CONFIG.groups[visibilityGroupIndex];
    var hasMembers = false;
    var hasVisibleMembers = false;
    for (var visibilityLayerIndex = 0; visibilityLayerIndex < CONFIG.layers.length; visibilityLayerIndex++) {
        var visibilitySpec = CONFIG.layers[visibilityLayerIndex];
        if (visibilitySpec.group === visibilityGroupName) {
            hasMembers = true;
            if (visibilitySpec.visible) hasVisibleMembers = true;
        }
    }
    if (hasMembers && !hasVisibleMembers) groups[visibilityGroupName].visible = false;
}

var outputFile = new File(CONFIG.output);
var saveOptions = new PhotoshopSaveOptions();
saveOptions.layers = true;
saveOptions.alphaChannels = true;
doc.saveAs(outputFile, saveOptions, false, Extension.LOWERCASE);
app.preferences.rulerUnits = previousUnits;
doc.close(SaveOptions.DONOTSAVECHANGES);

var persistedDoc = app.open(outputFile);
var validation = validateDocument(persistedDoc);
if (!CONFIG.open_after_build) persistedDoc.close(SaveOptions.DONOTSAVECHANGES);
"ok=" + (outputFile.exists && validation.ok) +
    ";output=" + outputFile.name +
    ";layer_count=" + CONFIG.layers.length +
    ";group_count=" + CONFIG.groups.length +
    ";kept_open=" + CONFIG.open_after_build +
    ";validated_after_reopen=true" +
    ";dimensions_match=" + validation.dimensions_match +
    ";actual_group_count=" + validation.actual_group_count +
    ";actual_layer_count=" + validation.actual_layer_count +
    ";missing_group_count=" + validation.missing_group_count +
    ";missing_layer_count=" + validation.missing_layer_count +
    ";visibility_mismatch_count=" + validation.visibility_mismatch_count +
    ";lock_mismatch_count=" + validation.lock_mismatch_count +
    ";empty_layer_count=" + validation.empty_layer_count;
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
        bridge = "photoshop_com_jsx"
        task = "build_smart_cutout_psd"
        output = [string]$result["output"]
        output_dir = "examples/output/photoshop"
        layer_count = [int]$result["layer_count"]
        group_count = [int]$result["group_count"]
        kept_open = $result["kept_open"] -eq "true"
        validated_after_reopen = $result["validated_after_reopen"] -eq "true"
        dimensions_match = $result["dimensions_match"] -eq "true"
        actual_group_count = [int]$result["actual_group_count"]
        actual_layer_count = [int]$result["actual_layer_count"]
        missing_group_count = [int]$result["missing_group_count"]
        missing_layer_count = [int]$result["missing_layer_count"]
        visibility_mismatch_count = [int]$result["visibility_mismatch_count"]
        lock_mismatch_count = [int]$result["lock_mismatch_count"]
        empty_layer_count = [int]$result["empty_layer_count"]
        private_paths_recorded = $false
    }
} catch {
    $safeMessage = [string]$_.Exception.Message
    $safeMessage = $safeMessage -replace [regex]::Escape($repoRoot), "<REPO_ROOT>"
    $safeMessage = $safeMessage -replace [regex]::Escape($manifestDir), "<JOB_DIR>"
    Write-Result @{
        ok = $false
        bridge = "photoshop_com_jsx"
        task = "build_smart_cutout_psd"
        message = "Photoshop could not build the smart cutout PSD."
        error_type = $_.Exception.GetType().Name
        error_detail = $safeMessage
        private_paths_recorded = $false
    }
}
