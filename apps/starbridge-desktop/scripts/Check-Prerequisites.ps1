[CmdletBinding()]
param([switch]$Json)

$ErrorActionPreference = "Stop"
$desktopRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repoRoot = [IO.Path]::GetFullPath((Join-Path $desktopRoot "..\.."))

function Command-Version {
    param([string]$Command, [string[]]$Arguments)

    $found = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $found) {
        return $null
    }
    try {
        return ((& $found.Source @Arguments 2>$null | Select-Object -First 1) -join "").Trim()
    }
    catch {
        return $null
    }
}

$nodeVersion = Command-Version -Command "node" -Arguments @("--version")
$npmVersion = Command-Version -Command "npm.cmd" -Arguments @("--version")
$pythonVersion = Command-Version -Command "python" -Arguments @("--version")
$rustVersion = Command-Version -Command "rustc" -Arguments @("--version")
$cargoVersion = Command-Version -Command "cargo" -Arguments @("--version")
$rustHost = $null
if ($rustVersion) {
    $hostLine = & rustc -Vv 2>$null | Where-Object { $_ -like "host:*" } | Select-Object -First 1
    if ($hostLine) {
        $rustHost = ($hostLine -split ":", 2)[1].Trim()
    }
}

$projectVenv = Test-Path -LiteralPath (Join-Path $repoRoot ".venv\Scripts\python.exe") -PathType Leaf
$buildPython = Join-Path $repoRoot ".venv-build\Scripts\python.exe"
$buildVenv = Test-Path -LiteralPath $buildPython -PathType Leaf
$pyInstallerVersion = $null
if ($buildVenv) {
    try {
        $pyInstallerVersion = (& $buildPython -m PyInstaller --version 2>$null | Select-Object -First 1).Trim()
    }
    catch {
        $pyInstallerVersion = $null
    }
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
$cppBuildTools = $false
$visualStudioInstall = $null
if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
    $visualStudioInstall = & $vswhere `
        -latest `
        -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath 2>$null | Select-Object -First 1
    $cppBuildTools = -not [string]::IsNullOrWhiteSpace($visualStudioInstall)
}

$webViewCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"),
    (Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) }
$webViewVersion = $null
foreach ($candidate in $webViewCandidates) {
    $versionDirectory = Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^\d+(\.\d+)+$" } |
        Sort-Object { [Version]$_.Name } -Descending |
        Select-Object -First 1
    if ($versionDirectory) {
        $webViewVersion = $versionDirectory.Name
        break
    }
}

$stableMsvc = $rustHost -like "*-pc-windows-msvc"
$nativeReady = [bool]($rustVersion -and $cargoVersion -and $stableMsvc -and $cppBuildTools -and $webViewVersion)
$result = [ordered]@{
    node = [ordered]@{ available = [bool]$nodeVersion; version = $nodeVersion }
    npm = [ordered]@{ available = [bool]$npmVersion; version = $npmVersion }
    python = [ordered]@{ available = [bool]$pythonVersion; version = $pythonVersion }
    project_venv = [ordered]@{ available = $projectVenv }
    build_venv = [ordered]@{ available = $buildVenv }
    pyinstaller = [ordered]@{ available = [bool]$pyInstallerVersion; version = $pyInstallerVersion }
    rustc = [ordered]@{ available = [bool]$rustVersion; version = $rustVersion; host = $rustHost }
    cargo = [ordered]@{ available = [bool]$cargoVersion; version = $cargoVersion }
    stable_msvc = [ordered]@{ available = $stableMsvc }
    cpp_build_tools = [ordered]@{ available = $cppBuildTools }
    webview2_runtime = [ordered]@{ available = [bool]$webViewVersion; version = $webViewVersion }
    native_tauri_ready = $nativeReady
}

if ($Json) {
    $result | ConvertTo-Json -Depth 4
}
else {
    $result.GetEnumerator() | ForEach-Object {
        $value = $_.Value
        if ($value -is [Collections.IDictionary]) {
            [PSCustomObject]@{
                Component = $_.Key
                Available = $value.available
                Version = $value.version
            }
        }
    } | Format-Table -AutoSize
    Write-Host "Native Tauri build ready: $nativeReady"
}

if (-not $nativeReady) {
    exit 2
}
