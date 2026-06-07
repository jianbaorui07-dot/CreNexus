param(
    [switch]$ProbeCom
)

$ErrorActionPreference = "Stop"

function Test-Key {
    param([string]$Path)
    return Test-Path -LiteralPath $Path
}

function Get-CommonPhotoshopPaths {
    $programFiles = [Environment]::GetFolderPath("ProgramFiles")
    $candidates = @(
        @{ label = "Adobe Photoshop 2026 default install"; path = Join-Path $programFiles "Adobe\Adobe Photoshop 2026\Photoshop.exe" },
        @{ label = "Adobe Photoshop 2025 default install"; path = Join-Path $programFiles "Adobe\Adobe Photoshop 2025\Photoshop.exe" },
        @{ label = "Adobe Photoshop 2024 default install"; path = Join-Path $programFiles "Adobe\Adobe Photoshop 2024\Photoshop.exe" },
        @{ label = "Adobe Photoshop 2023 default install"; path = Join-Path $programFiles "Adobe\Adobe Photoshop 2023\Photoshop.exe" }
    )

    foreach ($candidate in $candidates) {
        [pscustomobject]@{
            label = $candidate.label
            exists = Test-Path -LiteralPath $candidate.path
        }
    }
}

function Find-AdobePhotoshopExe {
    $roots = @(
        (Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "Adobe"),
        (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Adobe")
    )
    $found = @()
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            $found += Get-ChildItem -Path $root -Filter Photoshop.exe -Recurse -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty FullName
        }
    }
    return $found
}

$envPath = [Environment]::GetEnvironmentVariable("PHOTOSHOP_EXE")
$running = @(Get-Process -Name Photoshop -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{
        id = $_.Id
        process_name = $_.ProcessName
        executable = if ($_.Path) { Split-Path -Leaf $_.Path } else { $null }
        title = $_.MainWindowTitle
    }
})

$comRegistered = Test-Key "Registry::HKEY_CLASSES_ROOT\Photoshop.Application"
$clsidRegistered = Test-Key "Registry::HKEY_CLASSES_ROOT\Photoshop.Application\CLSID"
$comProbe = $null

if ($ProbeCom) {
    try {
        $app = New-Object -ComObject Photoshop.Application
        $raw = $app.DoJavaScript('"version=" + app.version + ";documents=" + app.documents.length;')
        $fields = @{}
        foreach ($part in ($raw -split ";")) {
            $pair = $part -split "=", 2
            if ($pair.Count -eq 2) {
                $fields[$pair[0]] = $pair[1]
            }
        }
        $comProbe = [pscustomobject]@{
            ok = $true
            version = $fields["version"]
            documents = $fields["documents"]
        }
    } catch {
        $comProbe = [pscustomobject]@{
            ok = $false
            error = $_.Exception.Message
        }
    }
}

$status = "needs_configuration"
if ($comRegistered -and $clsidRegistered) {
    $status = "com_registered"
}
if ($comProbe -and $comProbe.ok) {
    $status = "ready"
}

[pscustomobject]@{
    ok = ($status -eq "ready" -or $status -eq "com_registered")
    status = $status
    env_photoshop_exe = [bool]$envPath
    env_photoshop_exe_exists = [bool]($envPath -and (Test-Path -LiteralPath $envPath))
    com_registered = $comRegistered
    clsid_registered = $clsidRegistered
    running_processes = $running
    common_paths = @(Get-CommonPhotoshopPaths)
    discovered_path_count = @((Find-AdobePhotoshopExe)).Count
    com_probe = $comProbe
    next_step = if ($status -eq "ready") {
        "Run run_local_practice.ps1 or document_info.ps1."
    } elseif ($status -eq "com_registered") {
        "Run with -ProbeCom to verify Photoshop automation."
    } else {
        "Install and authorize Photoshop, then verify COM registration."
    }
} | ConvertTo-Json -Depth 8
