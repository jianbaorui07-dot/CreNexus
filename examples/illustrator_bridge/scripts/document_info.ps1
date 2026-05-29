param(
    [bool]$ProbeCom = $true
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Result)
    $Result | ConvertTo-Json -Depth 12
}

if (-not $ProbeCom) {
    Write-JsonResult @{
        ok = $false
        bridge = "illustrator"
        task = "document_info"
        active_document = $false
        warnings = @("COM probing was skipped by request.")
        next_steps = @("Run without ProbeCom=false on a Windows machine with Illustrator available.")
    }
    exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$jsxPath = Join-Path $repoRoot "examples\illustrator_bridge\jsx\document_info.jsx"

try {
    $app = New-Object -ComObject Illustrator.Application
    $jsx = Get-Content -Raw -Path $jsxPath
    $raw = $app.DoJavaScript($jsx)
    $parsed = $raw | ConvertFrom-Json
    $parsed | ConvertTo-Json -Depth 12
} catch {
    Write-JsonResult @{
        ok = $false
        bridge = "illustrator"
        task = "document_info"
        active_document = $false
        warnings = @("Could not connect to Illustrator.Application COM or run the document info JSX.")
        next_steps = @(
            "Start an authorized Illustrator desktop session.",
            "Open a document manually if you want current document metadata.",
            "Run npm.cmd run illustrator:info again."
        )
        error_type = $_.Exception.GetType().Name
    }
    exit 0
}
