[CmdletBinding()]
param(
    [string]$TargetTriple,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TargetTriple)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CARGO_BUILD_TARGET)) {
        $TargetTriple = $env:CARGO_BUILD_TARGET
    }
    elseif (Get-Command rustc -ErrorAction SilentlyContinue) {
        $hostLine = & rustc -Vv 2>$null | Where-Object { $_ -like "host:*" } | Select-Object -First 1
        if ($hostLine) {
            $TargetTriple = ($hostLine -split ":", 2)[1].Trim()
        }
    }
    if ([string]::IsNullOrWhiteSpace($TargetTriple)) {
        $architecture = if ($env:PROCESSOR_ARCHITEW6432) {
            $env:PROCESSOR_ARCHITEW6432
        }
        else {
            $env:PROCESSOR_ARCHITECTURE
        }
        $TargetTriple = switch ($architecture.ToUpperInvariant()) {
            "AMD64" { "x86_64-pc-windows-msvc" }
            "ARM64" { "aarch64-pc-windows-msvc" }
            "X86" { "i686-pc-windows-msvc" }
            default { throw "Could not infer the current Windows target triple. Pass -TargetTriple explicitly." }
        }
    }
}

if ($TargetTriple -notmatch "^[A-Za-z0-9_.-]+$") {
    throw "TargetTriple contains unsupported characters."
}

$desktopRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repoRoot = [IO.Path]::GetFullPath((Join-Path $desktopRoot "..\.."))
$buildEnvironment = Join-Path $repoRoot ".venv-build"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
$specFile = Join-Path $PSScriptRoot "starbridge-sidecar.spec"
$requirementsFile = Join-Path $PSScriptRoot "requirements-sidecar-build.txt"
$buildRoot = Join-Path $desktopRoot "build\sidecar"
$distRoot = Join-Path $buildRoot "dist"
$workRoot = Join-Path $buildRoot "work"
$sourceFolder = Join-Path $distRoot "starbridge-sidecar"
$sourceExecutable = Join-Path $sourceFolder "starbridge-sidecar.exe"
$binariesRoot = [IO.Path]::GetFullPath((Join-Path $desktopRoot "src-tauri\binaries"))
$stagedExecutable = Join-Path $binariesRoot "starbridge-sidecar-$TargetTriple.exe"

function Assert-PathWithinDesktop {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = [IO.Path]::GetFullPath($Path)
    $prefix = $desktopRoot.TrimEnd("\") + "\"
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing filesystem operation outside the desktop app directory."
    }
}

Assert-PathWithinDesktop -Path $buildRoot
Assert-PathWithinDesktop -Path $binariesRoot

if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python was not found. Install a supported Python version or make it available on PATH."
    }
    & $python.Source -m venv $buildEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the repository-local .venv-build environment."
    }
}

if (-not $SkipDependencyInstall) {
    & $buildPython -m pip install --disable-pip-version-check -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the pinned PyInstaller build dependency."
    }
    & $buildPython -m pip install --disable-pip-version-check --no-deps -e $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install StarBridge into .venv-build."
    }
}

& $buildPython -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is unavailable in .venv-build. Run again without -SkipDependencyInstall."
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $distRoot `
    --workpath $workRoot `
    $specFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller did not produce the StarBridge sidecar. Review the build output above."
}

if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "Expected sidecar executable was not found after PyInstaller completed."
}

New-Item -ItemType Directory -Path $binariesRoot -Force | Out-Null
Get-ChildItem -LiteralPath $binariesRoot -Force |
    Where-Object { $_.Name -ne "README.md" } |
    ForEach-Object {
        Assert-PathWithinDesktop -Path $_.FullName
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }

Copy-Item -LiteralPath $sourceExecutable -Destination $stagedExecutable -Force
$sourceInternal = Join-Path $sourceFolder "_internal"
if (-not (Test-Path -LiteralPath $sourceInternal -PathType Container)) {
    throw "PyInstaller one-folder output is missing its _internal directory."
}
Copy-Item -LiteralPath $sourceInternal -Destination (Join-Path $binariesRoot "_internal") -Recurse

$result = [ordered]@{
    ok = $true
    packaging_mode = "one-folder"
    target_triple = $TargetTriple
    executable = "src-tauri/binaries/starbridge-sidecar-$TargetTriple.exe"
    support_directory = "src-tauri/binaries/_internal"
    pyinstaller_environment = ".venv-build"
    community_vectorization_included = $true
    vectorflow_gui_included = $false
}
$result | ConvertTo-Json
