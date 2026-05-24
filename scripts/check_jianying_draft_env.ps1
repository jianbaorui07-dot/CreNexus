$ErrorActionPreference = "Stop"

Write-Output "StarBridge Jianying/CapCut draft environment check"
Write-Output "Mode: read-only"

$vars = @("JIANYING_DRAFTS_DIR", "CAPCUT_DRAFTS_DIR", "STARBRIDGE_JIANYING_SAFE_OUTPUT_DIR")
foreach ($name in $vars) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Output "${name}: not configured"
        continue
    }

    $exists = Test-Path -LiteralPath $value
    Write-Output "${name}: configured"
    Write-Output "  exists: $exists"
}

Write-Output "Safety: this script does not create, modify, or delete drafts."
Write-Output "Next: use examples\jianying\generate_draft_plan.py for a safe plan-only demo."
