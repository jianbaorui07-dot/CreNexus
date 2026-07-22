param(
    [switch]$Bootstrap,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Test-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    [ordered]@{
        name = $Name
        found = $null -ne $cmd
        source = $(if ($cmd) { $cmd.Name } else { $null })
    }
}

function Test-EnvPath {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    [ordered]@{
        name = $Name
        configured = [bool]$value
        exists = $(if ($value) { Test-Path -LiteralPath $value } else { $false })
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

function Invoke-Step {
    param(
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments
    )

    if ($DryRun) {
        return [ordered]@{
            label = $Label
            command = "$Command $($Arguments -join ' ')"
            status = "planned"
        }
    }

    & $Command @Arguments
    return [ordered]@{
        label = $Label
        command = "$Command $($Arguments -join ' ')"
        status = "completed"
    }
}

$bootstrapResults = @()
if ($Bootstrap) {
    if (-not (Test-Path -LiteralPath $venvPath)) {
        $bootstrapResults += Invoke-Step "create virtual environment" "python" @("-m", "venv", ".venv")
    } else {
        $bootstrapResults += [ordered]@{
            label = "create virtual environment"
            command = "python -m venv .venv"
            status = "skipped_existing"
        }
    }

    $pythonForInstall = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
    $bootstrapResults += Invoke-Step "upgrade pip" $pythonForInstall @("-m", "pip", "install", "--upgrade", "pip")
    $bootstrapResults += Invoke-Step "install dev dependencies" $pythonForInstall @("-m", "pip", "install", "-r", "requirements-dev.txt")
    $bootstrapResults += Invoke-Step "install package editable" $pythonForInstall @("-m", "pip", "install", "-e", ".")
}

$checks = [ordered]@{
    repo = "CreNexus"
    mode = $(if ($Bootstrap) { "bootstrap" } else { "check" })
    dry_run = [bool]$DryRun
    venv = [ordered]@{
        path = ".venv"
        exists = Test-Path -LiteralPath $venvPath
        python = $(if (Test-Path -LiteralPath $venvPython) { ".venv\Scripts\python.exe" } else { $null })
    }
    bootstrap = $bootstrapResults
    tools = @(
        Test-Command "python"
        Test-Command "node"
        Test-Command "npm.cmd"
        Test-Command "git"
        Test-Command "powershell"
    )
    python = [ordered]@{
        version = (& python --version 2>$null)
        venv_module = (& python -c "import venv; print('ok')" 2>$null)
    }
    env_paths = @(
        Test-EnvPath "STARBRIDGE_DOWNLOAD_INBOX"
        Test-EnvPath "COMFY_ROOT"
        Test-EnvPath "COMFY_LAUNCHER"
        Test-EnvPath "BLENDER_EXE"
        Test-EnvPath "BLENDER_MCP_DIR"
        Test-EnvPath "AUTOCAD_EXE"
        Test-EnvPath "DRAWIO_EXE"
        Test-EnvPath "PHOTOSHOP_EXE"
        Test-EnvPath "ILLUSTRATOR_EXE"
        Test-EnvPath "JIANYING_EXE"
        Test-EnvPath "JIANYING_DRAFTS_DIR"
        Test-EnvPath "CAPCUT_EXE"
        Test-EnvPath "CAPCUT_DRAFTS_DIR"
    )
    next_steps = @(
        "For isolated dependencies, run python -m venv .venv and activate it manually.",
        "Desktop software, Adobe licensing, AutoCAD licensing, ComfyUI models, and Jianying/CapCut installs remain manual.",
        "Keep real paths in local environment variables or a private .env file, never in the public repository."
    )
}

if ($Json) {
    $checks | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "CreNexus Windows local setup check"
Write-Host "Repository: $repoRoot"
Write-Host "Mode: $($checks.mode)"
Write-Host "Virtual environment: exists=$($checks.venv.exists), python=$($checks.venv.python)"
if ($Bootstrap) {
    Write-Host ""
    Write-Host "Bootstrap:"
    foreach ($step in $checks.bootstrap) {
        Write-Host ("- {0}: {1}" -f $step.label, $step.status)
    }
}
Write-Host ""
Write-Host "Required commands:"
foreach ($tool in $checks.tools) {
    Write-Host ("- {0}: {1}" -f $tool.name, $(if ($tool.found) { "found" } else { "missing" }))
}
Write-Host ""
Write-Host "Environment path hints:"
foreach ($item in $checks.env_paths) {
    Write-Host ("- {0}: configured={1}, exists={2}" -f $item.name, $item.configured, $item.exists)
}
Write-Host ""
Write-Host "Next steps:"
foreach ($step in $checks.next_steps) {
    Write-Host "- $step"
}
