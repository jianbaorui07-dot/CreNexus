$ErrorActionPreference = "Stop"

function Write-Check {
    param(
        [string]$Level,
        [string]$Name,
        [string]$Message
    )
    Write-Output ("{0}: {1} - {2}" -f $Level, $Name, $Message)
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$outputDir = Join-Path $repoRoot "examples\cad\output"

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    Write-Check "FAIL" "python" "python command was not found"
    exit 1
}
Write-Check "PASS" "python" "python command is available"

& python -c "import ezdxf" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Check "PASS" "ezdxf" "optional ezdxf dependency is installed"
} else {
    Write-Check "WARN" "ezdxf" "optional ezdxf dependency is not installed; dry-run still works"
}

if (Test-Path -LiteralPath $outputDir) {
    Write-Check "PASS" "examples/cad/output" "output directory exists"
} else {
    Write-Check "FAIL" "examples/cad/output" "output directory is missing"
    exit 1
}

Write-Check "PASS" "autocad" "real AutoCAD was not called"
