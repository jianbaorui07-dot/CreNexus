param(
    [string]$RepoRoot = "C:\codex-cad-bridge-git",
    [string]$WorkspaceRoot = "C:\cad_exact_trace_workspace",
    [string]$JobsRoot = "C:\cad_jobs",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$env:Path += ";C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI"

$exporter = Join-Path $RepoRoot "scripts\export_cad_trace_snapshot.py"
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python runtime not found: $PythonExe" }
if (-not (Test-Path -LiteralPath $RepoRoot)) { throw "Repo root not found: $RepoRoot" }
if (-not (Test-Path -LiteralPath $exporter)) { throw "Snapshot exporter not found: $exporter" }

& $PythonExe $exporter --workspace-root $WorkspaceRoot --jobs-root $JobsRoot --repo-root $RepoRoot
if ($LASTEXITCODE -ne 0) {
    throw "Snapshot export failed with exit code $LASTEXITCODE"
}

$userNameRaw = & git -C $RepoRoot config user.name
$userName = if ($null -eq $userNameRaw) { "" } else { "$userNameRaw".Trim() }
if (-not $userName) {
    git -C $RepoRoot config user.name "Codex CAD Sync" | Out-Null
}

$userEmailRaw = & git -C $RepoRoot config user.email
$userEmail = if ($null -eq $userEmailRaw) { "" } else { "$userEmailRaw".Trim() }
if (-not $userEmail) {
    git -C $RepoRoot config user.email "codex-cad-sync@users.noreply.github.com" | Out-Null
}

git -C $RepoRoot add -- scripts/export_cad_trace_snapshot.py scripts/sync_cad_trace_snapshot.ps1 scripts/register_cad_trace_sync_task.ps1 docs/cad_exact_trace_sync

$pending = (& git -C $RepoRoot status --porcelain).Trim()
if (-not $pending) {
    Write-Host "No CAD sync changes to commit."
    exit 0
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git -C $RepoRoot commit -m "chore: sync cad exact trace snapshot $timestamp" | Out-Host

$authOk = $true
try {
    & gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        $authOk = $false
    }
} catch {
    $authOk = $false
}

if (-not $authOk) {
    Write-Warning "GitHub auth is not configured yet. Snapshot committed locally but not pushed."
    exit 0
}

git -C $RepoRoot pull --rebase origin main | Out-Host
git -C $RepoRoot push origin main | Out-Host
Write-Host "CAD snapshot pushed to GitHub."
