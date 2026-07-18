param(
    [string]$Subproject,
    [switch]$NonInteractive,
    [switch]$DryRun,
    [switch]$Json,
    [switch]$SkipCodexConfig,
    [switch]$SkipNode
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$catalogPath = Join-Path $repoRoot "starbridge.projects.json"
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$codexConfigPath = Join-Path $repoRoot ".codex\config.toml"
$managedStart = "# >>> starbridge bootstrap managed block >>>"
$managedEnd = "# <<< starbridge bootstrap managed block <<<"

function ConvertTo-TomlString {
    param([string]$Value)
    return ($Value | ConvertTo-Json -Compress)
}

function Get-PythonCommand {
    foreach ($name in @("python", "python3", "py")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $candidate) {
            continue
        }
        try {
            $versionText = (& $candidate.Source --version 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -eq 0 -and $versionText -match "Python\s+(\d+)\.(\d+)(?:\.(\d+))?") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -eq 3 -and $minor -ge 10) {
                    return [ordered]@{
                        command = $candidate.Source
                        version = $versionText
                    }
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-RecordedCommand {
    param(
        [System.Collections.ArrayList]$Steps,
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $repoRoot
    )

    $display = "$Command $($Arguments -join ' ')"
    if ($DryRun) {
        [void]$Steps.Add([ordered]@{
            label = $Label
            command = $display
            status = "planned"
        })
        return
    }

    Push-Location $WorkingDirectory
    try {
        $output = (& $Command @Arguments 2>&1 | Out-String).Trim()
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "$Label failed (exit $exitCode): $output"
    }
    [void]$Steps.Add([ordered]@{
        label = $Label
        command = $display
        status = "completed"
        output = $(if ($output.Length -gt 500) { $output.Substring(0, 500) } else { $output })
    })
}

function Write-CodexConfig {
    param(
        [System.Collections.ArrayList]$Steps,
        [string]$PythonPath
    )

    $coordinatorPath = Join-Path $repoRoot "plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py"
    $pythonToml = ConvertTo-TomlString $PythonPath
    $coordinatorToml = ConvertTo-TomlString $coordinatorPath
    $block = @"
$managedStart
[mcp_servers.starbridge]
command = $pythonToml
args = ["-m", "starbridge_mcp.mcp_server"]

[mcp_servers.starbridge.env]
PYTHONUTF8 = "1"
STARBRIDGE_PHOTOSHOP_SAFE_ONLY = "1"
STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN = "1"
STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE = "0"

[mcp_servers.starbridge-version-coordinator]
command = $pythonToml
args = [$coordinatorToml]

[mcp_servers.starbridge-version-coordinator.env]
PYTHONUTF8 = "1"
STARBRIDGE_CONFIG_SAFE_ONLY = "1"
$managedEnd
"@

    if ($DryRun) {
        [void]$Steps.Add([ordered]@{
            label = "configure Codex MCP servers"
            command = "update .codex/config.toml managed block"
            status = "planned"
        })
        return
    }

    $configDirectory = Split-Path -Parent $codexConfigPath
    New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
    $current = if (Test-Path -LiteralPath $codexConfigPath) {
        Get-Content -Raw -Encoding utf8 $codexConfigPath
    } else {
        ""
    }
    $pattern = "(?ms)^" + [regex]::Escape($managedStart) + ".*?^" + [regex]::Escape($managedEnd) + "\r?\n?"
    $preserved = [regex]::Replace($current, $pattern, "").TrimEnd()
    $next = if ($preserved) { "$preserved`r`n`r`n$block`r`n" } else { "$block`r`n" }
    Set-Content -LiteralPath $codexConfigPath -Value $next -Encoding utf8
    [void]$Steps.Add([ordered]@{
        label = "configure Codex MCP servers"
        command = "update .codex/config.toml managed block"
        status = "completed"
    })
}

if (-not (Test-Path -LiteralPath $catalogPath)) {
    throw "Subproject catalog not found: $catalogPath"
}
$catalog = Get-Content -Raw -Encoding utf8 $catalogPath | ConvertFrom-Json
$projects = @($catalog.subprojects)
$projectIds = @($projects | ForEach-Object { $_.id })

if ($Subproject -and $Subproject -notin $projectIds) {
    throw "Unknown subproject '$Subproject'. Choose one of: $($projectIds -join ', ')"
}

$steps = [System.Collections.ArrayList]::new()
$python = Get-PythonCommand
if (-not $python -and -not $DryRun) {
    throw "Python 3.10 or newer was not found. Install Python, then run bootstrap.ps1 again."
}
$pythonCommand = if ($python) { $python.command } else { "python" }

if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-RecordedCommand $steps "create isolated Python environment" $pythonCommand @("-m", "venv", $venvPath)
} else {
    [void]$steps.Add([ordered]@{
        label = "create isolated Python environment"
        command = "$pythonCommand -m venv $venvPath"
        status = "skipped_existing"
    })
}

$installPython = if ((Test-Path -LiteralPath $venvPython) -or $DryRun) { $venvPython } else { $pythonCommand }
Invoke-RecordedCommand $steps "install StarBridge core" $installPython @("-m", "pip", "install", "--disable-pip-version-check", "-e", ".")
if (-not $SkipCodexConfig) {
    Write-CodexConfig $steps $installPython
}

if (-not $Subproject -and -not $NonInteractive -and -not $DryRun) {
    Write-Host ""
    Write-Host $catalog.question
    for ($index = 0; $index -lt $projects.Count; $index++) {
        Write-Host ("[{0}] {1} - {2}" -f ($index + 1), $projects[$index].label, $projects[$index].description)
    }
    $answer = Read-Host "Choose one subproject (enter its number or id)"
    if ($answer -match "^\d+$" -and [int]$answer -ge 1 -and [int]$answer -le $projects.Count) {
        $Subproject = $projects[[int]$answer - 1].id
    } elseif ($answer -in $projectIds) {
        $Subproject = $answer
    }
}

if (-not $Subproject) {
    $result = [ordered]@{
        ok = $true
        status = "needs_selection"
        question = $catalog.question
        selection_policy = $catalog.selection_policy
        choices = @($projects | ForEach-Object {
            [ordered]@{
                id = $_.id
                label = $_.label
                description = $_.description
            }
        })
        rerun = ".\bootstrap.ps1 -Subproject <id> -NonInteractive -Json"
        python = $(if ($python) { $python.version } else { "not detected during dry-run" })
        steps = $steps
    }
    if ($Json -or $NonInteractive -or $DryRun) {
        $result | ConvertTo-Json -Depth 8
    } else {
        Write-Host "No subproject selected; the core environment is ready."
    }
    exit 0
}

$selected = $projects | Where-Object { $_.id -eq $Subproject } | Select-Object -First 1
$extras = @($selected.python_extras)
if ($extras.Count -gt 0) {
    $extraSpec = ".[" + ($extras -join ",") + "]"
    Invoke-RecordedCommand $steps "install $Subproject Python partition" $installPython @(
        "-m", "pip", "install", "--disable-pip-version-check", "-e", $extraSpec
    )
}

$nodeProjects = @($selected.node_projects)
if ($nodeProjects.Count -gt 0 -and -not $SkipNode) {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        if ($DryRun) {
            $npmPath = "npm.cmd"
        } else {
            throw "The '$Subproject' partition needs Node.js/npm. Install Node.js LTS or rerun with -SkipNode."
        }
    } else {
        $npmPath = $npm.Source
    }
    foreach ($relativePath in $nodeProjects) {
        $nodeRoot = Join-Path $repoRoot $relativePath
        $npmAction = if (Test-Path -LiteralPath (Join-Path $nodeRoot "package-lock.json")) { "ci" } else { "install" }
        Invoke-RecordedCommand $steps "install $Subproject Node partition" $npmPath @($npmAction, "--no-audit", "--no-fund") $nodeRoot
    }
}

$smokeArgs = @($selected.smoke_test)
if ($smokeArgs.Count -gt 0) {
    Invoke-RecordedCommand $steps "verify $Subproject partition" $installPython $smokeArgs
}
Invoke-RecordedCommand $steps "verify version coordinator" $installPython @(
    "plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py", "self-test"
)

$result = [ordered]@{
    ok = $true
    status = $(if ($DryRun) { "planned" } else { "ready" })
    selected_subproject = $Subproject
    selected_label = $selected.label
    selection_policy = $catalog.selection_policy
    concurrent_install = $false
    python = $(if ($python) { $python.version } else { "not detected during dry-run" })
    venv = ".venv"
    codex_config = $(if ($SkipCodexConfig) { "skipped" } else { ".codex/config.toml" })
    steps = $steps
    next_step = "Start a new Codex task in this repository so the generated MCP configuration is loaded."
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
} else {
    Write-Host ""
    Write-Host ("StarBridge is ready: {0} ({1})" -f $selected.label, $Subproject)
    Write-Host "Only this partition was installed; no other subproject was started."
    Write-Host "Start a new Codex task in this repository to load the MCP servers."
}
