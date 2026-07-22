---
name: starbridge-macos-adapter
description: Audit a CreNexus checkout on macOS, run its safe cross-platform checks, and distinguish supported repository routes from unverified or Windows-only desktop paths. Use when adapting Windows-oriented CreNexus instructions for a Mac without changing system security settings or claiming unverified Adobe support.
---

# CreNexus macOS 适配审计

本 Skill 只覆盖 macOS 环境审计、公开仓库的安全核心检查和能力边界说明；它**不**使 CreNexus 的桌面链路自动获得 macOS 支持。桌面软件、Apple Events、Tauri、sidecar、CI 或安装脚本的适配，必须作为独立阶段并以实际验证为准。

## 先做安全预检

在仓库根目录执行只读预检；它不安装依赖、不访问 Adobe、也不输出本机绝对路径：

```bash
zsh .codex/skills/starbridge-macos-adapter/scripts/preflight.sh --soft-exit
```

先检查 `git status --short`。保留所有已有 dirty/untracked 文件；不得 `reset`、`clean`、`stash`，也不要把本机配置、构建产物或客户资产加入提交。

## 核心边界

- 使用 `python3`、POSIX 路径、zsh 和裸 `npm`；不要把 `npm.cmd`、盘符路径、Windows COM 或 PowerShell 命令改名后当作 macOS 实现。
- 不自动安装 Homebrew、Xcode Command Line Tools、Rosetta，或更改 Gatekeeper、SIP、TCC、Automation、Accessibility、Screen Recording、Full Disk Access、防火墙或登录状态。
- 不扫描 Desktop、Documents、Downloads、Library、Adobe 工程目录、Creative Cloud 缓存或客户文件；只操作当前仓库和用户明确提供的公开输入。
- 不把 Illustrator/Photoshop 的“未安装、未授权、未打开或未在 macOS 验证”说成成功。不要生成 AppleScript、任意 JSX/BatchPlay，或执行真实导出。
- 普通客户的图片转矢量仍须遵守 `$starbridge-illustrator-mcp` 的“先精确像素重建、后绘制型矢量”流程；绝不使用 Illustrator Image Trace 作为默认或失败回退。

## 安全核心检查

当当前 Python 环境已具备项目依赖时，优先运行下列不需要桌面软件的命令：

```bash
python3 scripts/security_check.py
python3 examples/bridge_status.py --json --redact-paths --soft-exit
python3 -m starbridge_mcp.server tools --json --safe-only
python3 plugins/starbridge-version-coordinator/scripts/version_coordinator_mcp.py self-test
```

若要覆盖 Illustrator Node proxy 的协议测试，先确认该测试所需的 Node 依赖已在当前仓库安装；否则将其报告为跳过，而不是安装或伪造通过：

```bash
python3 -m unittest tests.test_illustrator_realtime_proxy tests.test_version_coordinator_plugin
```

## 桌面软件路由

阅读 [references/compatibility.md](references/compatibility.md) 后再描述桌面能力。

- Illustrator、SVG/AI、艺术板和矢量交付请求，转交 `$starbridge-illustrator-mcp`；当前仓库中现有的 realtime adapter 启动入口是 PowerShell，不可据此宣称已有 macOS 原生 bridge。
- Photoshop 请求转交 `$starbridge-photoshop-mcp`；该 Skill 不新增 Photoshop AppleScript 路线。
- AutoCAD COM、WGC capture 和其他 Windows-only 路线在 macOS 上应报告 `unsupported_platform` 或 `remote_executor_required`。
- 版本协调器的 Python `self-test` 可用于离线验证；计划或迁移操作仍须遵循调用方的显式确认和安全模式，不能当作安装、许可检查或系统改写。

## 完成报告

报告 macOS 架构与依赖状态、实际运行的命令及结果、已验证的安全核心、跳过/未验证的桌面路由，以及 Windows-only 边界。明确区分“源码存在”“本机已验证”和“后续阶段计划”；不要写入或导出用户资产。
