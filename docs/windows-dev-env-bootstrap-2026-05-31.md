# Windows Development Environment Bootstrap

Date: 2026-05-31

This note records a Windows development-environment bootstrap process used during local setup work. It is intentionally public-safe: local absolute paths, private assets, and machine-specific workspace details are omitted.

## Goal

Prepare a practical local development baseline with:

- Git
- Node.js and npm
- Python and pip
- pnpm / yarn
- Visual Studio Code
- .NET SDK
- GitHub CLI
- Visual Studio Build Tools
- Optional Go, Rust, JDK, Maven, Gradle, and WSL Ubuntu

## Initial Audit Pattern

Use a read-only tool check before installing anything:

```powershell
$tools = @(
  'git','node','npm','pnpm','yarn','python','py','pip','uv',
  'go','rustc','cargo','java','javac','mvn','gradle','dotnet',
  'code','winget','choco','scoop','docker','gh'
)

$rows = foreach ($tool in $tools) {
  $cmd = Get-Command $tool -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) {
    try {
      $version = if ($tool -eq 'npm') {
        & npm.cmd --version 2>$null | Select-Object -First 1
      } else {
        & $tool --version 2>$null | Select-Object -First 1
      }
    } catch {
      $version = 'installed'
    }
    [pscustomobject]@{ Tool = $tool; Version = $version; Path = $cmd.Source }
  } else {
    [pscustomobject]@{ Tool = $tool; Version = 'MISSING'; Path = '' }
  }
}

$rows | Format-Table -AutoSize
```

## Fix Applied

PowerShell was blocking npm shim execution, so the current-user execution policy was changed:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
npm --version
```

## Common Blockers

The setup run found these blockers:

- `winget` was unavailable.
- Python was not installed, even though the `py` launcher existed.
- `pnpm` and `yarn` were unavailable until Corepack could fetch/activate them.
- Docker CLI existed, but Docker Desktop / daemon needed to be running before Docker commands were usable.
- Administrator elevation from the automation session failed, so UAC confirmation had to be performed manually.
- Network access to package sources must work before online installers can complete.

## Administrator Bootstrap Script

Run this from an elevated PowerShell after `winget` / Microsoft App Installer is available:

```powershell
[CmdletBinding()]
param(
  [switch]$Extended,
  [switch]$Wsl
)

$ErrorActionPreference = 'Continue'

function Step {
  param([string]$Message)
  Write-Host ''
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function HasCommand {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WingetPackage {
  param(
    [string]$Id,
    [string]$Name,
    [string[]]$Override
  )

  Step "Installing $Name"
  $args = @(
    'install',
    '--id', $Id,
    '--exact',
    '--accept-source-agreements',
    '--accept-package-agreements',
    '--silent'
  )

  if ($Override) {
    $args += '--override'
    $args += ($Override -join ' ')
  }

  winget @args
}

Step 'Preparing PowerShell and npm directories'
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
New-Item -ItemType Directory -Force "$env:APPDATA\npm", "$env:LOCALAPPDATA\npm-cache" | Out-Null
npm config set prefix "$env:APPDATA\npm"
npm config set cache "$env:LOCALAPPDATA\npm-cache"

Step 'Checking winget'
if (-not (HasCommand winget)) {
  Write-Warning 'winget is not available. Install or repair Microsoft App Installer first, then rerun this script.'
  Start-Process 'ms-windows-store://pdp/?ProductId=9NBLGGH4NNS1'
  exit 2
}

winget source update

$baseline = @(
  @{ Id = 'Git.Git'; Name = 'Git' },
  @{ Id = 'OpenJS.NodeJS.LTS'; Name = 'Node.js LTS' },
  @{ Id = 'Python.Python.3.13'; Name = 'Python 3.13' },
  @{ Id = 'Microsoft.VisualStudioCode'; Name = 'Visual Studio Code' },
  @{ Id = 'Microsoft.DotNet.SDK.8'; Name = '.NET SDK 8' },
  @{ Id = 'GitHub.cli'; Name = 'GitHub CLI' }
)

foreach ($pkg in $baseline) {
  Install-WingetPackage -Id $pkg.Id -Name $pkg.Name
}

Step 'Installing Visual Studio Build Tools C++ workload'
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --accept-source-agreements --accept-package-agreements --silent --override '--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'

if ($Extended) {
  $extendedPkgs = @(
    @{ Id = 'GoLang.Go'; Name = 'Go' },
    @{ Id = 'Rustlang.Rustup'; Name = 'Rustup' },
    @{ Id = 'EclipseAdoptium.Temurin.21.JDK'; Name = 'JDK 21' },
    @{ Id = 'Apache.Maven'; Name = 'Maven' },
    @{ Id = 'Gradle.Gradle'; Name = 'Gradle' }
  )

  foreach ($pkg in $extendedPkgs) {
    Install-WingetPackage -Id $pkg.Id -Name $pkg.Name
  }
}

if ($Wsl) {
  Step 'Installing WSL Ubuntu'
  wsl --install Ubuntu
}

Step 'Enabling Corepack package managers'
corepack enable
corepack prepare pnpm@latest --activate
corepack prepare yarn@stable --activate

Step 'Verification'
$tools = @('git','node','npm','pnpm','yarn','python','py','pip','dotnet','code','gh','docker')
if ($Extended) {
  $tools += @('go','rustc','cargo','java','javac','mvn','gradle')
}

foreach ($tool in $tools) {
  $cmd = Get-Command $tool -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) {
    try {
      $version = & $tool --version 2>$null | Select-Object -First 1
    } catch {
      $version = 'installed'
    }
    '{0,-10} {1}' -f $tool, $version
  } else {
    '{0,-10} MISSING' -f $tool
  }
}
```

## Verification Commands

```powershell
git --version
node --version
npm --version
pnpm --version
yarn --version
python --version
pip --version
dotnet --info
code --version
gh --version
docker --version
```

## Notes

- Keep generated logs and machine-specific paths out of commits.
- Do not commit local npm cache directories, downloaded installers, design assets, PSD files, AI files, fonts, or private workspace paths.
- Prefer tolerant checks that report `missing`, `skipped`, or `not configured` instead of failing hard when optional local software is absent.
