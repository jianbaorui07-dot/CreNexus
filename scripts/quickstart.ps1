[CmdletBinding()]
param(
    [ValidateSet("auto", "core", "standard", "all")]
    [string]$Profile = "auto",
    [switch]$SkipNode,
    [switch]$SkipCodexConfig,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Escape-TomlBasicString {
    param([string]$Value)
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

function Add-Step {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Name,
        [string]$Status,
        [string]$Detail = ""
    )
    [void]$List.Add([ordered]@{
        name = $Name
        status = $Status
        detail = $Detail
    })
}

function Invoke-Checked {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Name,
        [string]$Command,
        [string[]]$Arguments
    )

    if ($DryRun) {
        Add-Step $List $Name "planned" (($Command + " " + ($Arguments -join " ")).Trim())
        return
    }

    if ($Json) {
        $captured = (& $Command @Arguments 2>&1 | Out-String).Trim()
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "$Name failed (exit $exitCode): $captured"
        }
        Add-Step $List $Name "completed" (($captured -split "`r?`n" | Select-Object -Last 1) -join "")
        return
    }

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (exit $LASTEXITCODE)."
    }
    Add-Step $List $Name "completed"
}

function Find-Python {
    $candidates = @(
        @{ command = "py"; prefix = @("-3") },
        @{ command = "python"; prefix = @() },
        @{ command = "python3"; prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $resolved = Get-Command $candidate.command -ErrorAction SilentlyContinue
        if (-not $resolved) { continue }
        $versionText = (& $resolved.Source @($candidate.prefix) --version 2>&1 | Out-String).Trim()
        if ($versionText -match "Python\s+(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if (($major -gt 3) -or ($major -eq 3 -and $minor -ge 10)) {
                return [ordered]@{
                    command = $resolved.Source
                    prefix = @($candidate.prefix)
                    version = $versionText
                }
            }
        }
    }
    throw "Python 3.10+ was not found. Install Python 3.10-3.13 and run this command again."
}

function Get-FeatureExtras {
    param([string]$RequestedProfile)

    $extras = [System.Collections.Generic.List[string]]::new()
    [void]$extras.Add("dev")
    [void]$extras.Add("vectorization")

    if ($RequestedProfile -in @("standard", "all")) {
        [void]$extras.Add("cad")
        [void]$extras.Add("comfy")
        [void]$extras.Add("adobe")
        [void]$extras.Add("illustrator-vector")
    }
    if ($RequestedProfile -eq "all") {
        [void]$extras.Add("illustrator-trace")
        [void]$extras.Add("vector-refinement")
        [void]$extras.Add("vector-app")
    }

    return @($extras | Select-Object -Unique)
}

function Test-FeatureHint {
    $names = @(
        "PHOTOSHOP_EXE", "ILLUSTRATOR_EXE", "AUTOCAD_EXE", "BLENDER_EXE",
        "COMFY_ROOT", "STARBRIDGE_COMFYUI_URL", "JIANYING_EXE", "CAPCUT_EXE"
    )
    foreach ($name in $names) {
        if ([Environment]::GetEnvironmentVariable($name)) { return $true }
    }
    foreach ($name in @("blender", "acad", "photoshop", "illustrator", "jianying", "capcut")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

$repoRoot = Resolve-RepoRoot
$steps = [System.Collections.ArrayList]::new()
$warnings = [System.Collections.Generic.List[string]]::new()
$python = Find-Python
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

$effectiveProfile = $Profile
if ($Profile -eq "auto") {
    # Auto keeps first install short while still installing the headless vector path.
    # Users with desktop software can opt into standard/all without changing the repo.
    $effectiveProfile = if (Test-FeatureHint) { "standard" } else { "core" }
}
$extras = Get-FeatureExtras $effectiveProfile

if (-not (Test-Path -LiteralPath $venvPath)) {
    Invoke-Checked $steps "create virtual environment" $python.command (@($python.prefix) + @("-m", "venv", $venvPath))
} else {
    Add-Step $steps "create virtual environment" "skipped_existing" $venvPath
}

if (-not $DryRun -and -not (Test-Path -LiteralPath $venvPython)) {
    throw "The virtual environment was not created at $venvPython."
}

$installSpec = ".[" + ($extras -join ",") + "]"
Invoke-Checked $steps "upgrade pip" $venvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $steps "install Python extras" $venvPython @("-m", "pip", "install", $installSpec)

$proxyRoots = @(
    (Join-Path $repoRoot "node_proxy\photoshop-bridge"),
    (Join-Path $repoRoot "node_proxy\illustrator-bridge")
)
$desktopRoot = Join-Path $repoRoot "apps\starbridge-desktop"
$node = Get-Command "node" -ErrorAction SilentlyContinue
$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if (-not $SkipNode) {
    if ($node -and $npm) {
        if (Test-Path -LiteralPath (Join-Path $desktopRoot "package-lock.json")) {
            Invoke-Checked $steps "install desktop dependencies" $npm.Source @(
                "ci", "--prefix", $desktopRoot, "--no-audit", "--no-fund"
            )
        }
        if ($effectiveProfile -in @("standard", "all")) {
            foreach ($proxyRoot in $proxyRoots) {
                if (Test-Path -LiteralPath (Join-Path $proxyRoot "package.json")) {
                    Invoke-Checked $steps "install Node bridge $(Split-Path $proxyRoot -Leaf)" $npm.Source @(
                        "install", "--prefix", $proxyRoot, "--no-package-lock", "--no-audit", "--no-fund"
                    )
                }
            }
        }
    } else {
        [void]$warnings.Add("Node.js/npm not found; desktop dependencies and UXP Node proxies were not installed. Python/MCP flows remain available.")
    }
}

if (-not $SkipCodexConfig) {
    $configPath = Join-Path $repoRoot ".codex\config.toml"
    $pythonToml = Escape-TomlBasicString $venvPython
    $rootToml = Escape-TomlBasicString $repoRoot
    $coordinatorToml = Escape-TomlBasicString (Join-Path $repoRoot "plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py")
    $block = @"

# BEGIN STARBRIDGE QUICKSTART (managed by scripts/quickstart.ps1)
[mcp_servers.starbridge]
command = "$pythonToml"
args = ["-m", "starbridge_mcp.mcp_server"]
cwd = "$rootToml"

[mcp_servers.starbridge.env]
STARBRIDGE_PHOTOSHOP_SAFE_ONLY = "1"
STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN = "1"
STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE = "0"

[mcp_servers.starbridge-version-coordinator]
command = "$pythonToml"
args = ["$coordinatorToml"]
cwd = "$rootToml"
# END STARBRIDGE QUICKSTART
"@
    $configDir = Split-Path $configPath -Parent
    if (-not (Test-Path -LiteralPath $configDir)) {
        if (-not $DryRun) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }
    }
    if ($DryRun) {
        Add-Step $steps "configure Codex MCP" "planned" $configPath
    } else {
        $existing = if (Test-Path -LiteralPath $configPath) { Get-Content -Raw -Encoding utf8 $configPath } else { "" }
        $pattern = "(?ms)\r?\n?# BEGIN STARBRIDGE QUICKSTART.*?# END STARBRIDGE QUICKSTART\r?\n?"
        $updated = [regex]::Replace($existing, $pattern, "")
        # Windows PowerShell's `Set-Content -Encoding utf8` emits a BOM.  TOML
        # consumers used by Codex/Python expect UTF-8 without a BOM, so write
        # through .NET with an explicit BOM-free encoder.
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($configPath, ($updated.TrimEnd() + $block + "`r`n"), $utf8NoBom)
        Add-Step $steps "configure Codex MCP" "completed" $configPath
    }
}

Invoke-Checked $steps "verify Python package" $venvPython @("-c", "import starbridge_mcp; print('starbridge_mcp import: ok')")
Invoke-Checked $steps "verify version coordinator" $venvPython @(
    (Join-Path $repoRoot "plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py"), "self-test"
)
Invoke-Checked $steps "verify safe MCP tools" $venvPython @("-m", "starbridge_mcp.server", "tools", "--json", "--safe-only")

$result = [ordered]@{
    ok = $true
    repo = $repoRoot
    profile_requested = $Profile
    profile_applied = $effectiveProfile
    python = $python.version
    venv = ".venv\Scripts\python.exe"
    extras = $extras
    codex_config = $(if ($SkipCodexConfig) { $null } else { ".codex\config.toml" })
    steps = @($steps)
    warnings = @($warnings)
    next = @(
        "Open a new Codex task in this repository so it reloads .codex/config.toml.",
        "Use the version coordinator to probe capabilities; software version is advisory, not a whitelist.",
        "Run scripts\quickstart.ps1 -Profile standard or -Profile all when you need optional desktop bridges."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
} else {
    Write-Host "StarBridge quickstart completed ($effectiveProfile)."
    Write-Host "Python: $($python.version)"
    Write-Host "Virtual environment: $venvPath"
    Write-Host "Codex config: $(if ($SkipCodexConfig) { 'skipped' } else { Join-Path $repoRoot '.codex\config.toml' })"
    foreach ($step in $steps) {
        Write-Host ("- {0}: {1}" -f $step.name, $step.status)
    }
    foreach ($warning in $warnings) {
        Write-Warning $warning
    }
    Write-Host "Next: start a new Codex task in this repository."
}
