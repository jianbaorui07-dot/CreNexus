param()

$ErrorActionPreference = "Stop"

function Invoke-JsonScript {
    param([string]$ScriptPath, [string[]]$Arguments)
    $output = & powershell -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    $text = ($output | Out-String).Trim()
    if (-not $text) {
        throw "Script returned no JSON: $ScriptPath"
    }
    return $text | ConvertFrom-Json
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$createScript = Join-Path $PSScriptRoot "create_demo_artboard.ps1"
$exportScript = Join-Path $PSScriptRoot "export_demo_assets.ps1"
$manifestScript = Join-Path $repoRoot "examples\illustrator_bridge\write_demo_manifest.py"

$create = Invoke-JsonScript -ScriptPath $createScript -Arguments @("-ConfirmWrite")
$export = Invoke-JsonScript -ScriptPath $exportScript -Arguments @("-ConfirmExport")
$manifestRaw = & python $manifestScript
$manifest = (($manifestRaw | Out-String).Trim()) | ConvertFrom-Json

[pscustomobject]@{
    ok = [bool]($create.ok -and $export.ok -and $manifest.ok)
    bridge = "illustrator"
    task = "sandbox_vector_demo"
    create = $create
    export = $export
    manifest = $manifest
    warnings = @($create.warnings + $export.warnings + $manifest.warnings)
    next_steps = @($create.next_steps + $export.next_steps + $manifest.next_steps)
} | ConvertTo-Json -Depth 16
