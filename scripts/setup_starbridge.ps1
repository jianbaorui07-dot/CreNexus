param(
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Test-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    [ordered]@{
        name = $Name
        found = $null -ne $cmd
        source = if ($cmd) { $cmd.Source } else { $null }
    }
}

function Test-EnvPath {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    [ordered]@{
        name = $Name
        configured = [bool]$value
        exists = if ($value) { Test-Path -LiteralPath $value } else { $false }
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$checks = [ordered]@{
    repo = "StarBridge"
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
        Test-EnvPath "PHOTOSHOP_EXE"
        Test-EnvPath "ILLUSTRATOR_EXE"
        Test-EnvPath "JIANYING_EXE"
        Test-EnvPath "JIANYING_DRAFTS_DIR"
        Test-EnvPath "CAPCUT_EXE"
        Test-EnvPath "CAPCUT_DRAFTS_DIR"
    )
    next_steps = @(
        "如需隔离依赖，在仓库根目录运行 python -m venv .venv 后手动激活。",
        "大型桌面软件、Adobe 授权、AutoCAD 授权、ComfyUI 模型和剪映/CapCut 安装需要用户手动完成。",
        "把真实路径放在本机 .env 或 PowerShell 用户环境变量，不要写进公开仓库。"
    )
}

if ($Json) {
    $checks | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "StarBridge Windows 本机初始化检查"
Write-Host "仓库: $repoRoot"
Write-Host ""
Write-Host "基础命令:"
foreach ($tool in $checks.tools) {
    Write-Host ("- {0}: {1}" -f $tool.name, $(if ($tool.found) { "found" } else { "missing" }))
}
Write-Host ""
Write-Host "环境变量路径:"
foreach ($item in $checks.env_paths) {
    Write-Host ("- {0}: configured={1}, exists={2}" -f $item.name, $item.configured, $item.exists)
}
Write-Host ""
Write-Host "下一步:"
foreach ($step in $checks.next_steps) {
    Write-Host "- $step"
}
