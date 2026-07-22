# 给 Codex 的 3 分钟安装入口

把仓库链接发给 Codex 后，Windows 可直接告诉它：

```text
请克隆这个仓库，进入仓库后运行 .\bootstrap.ps1 -Profile auto。
安装完成后打开一个新的 Codex task，并使用仓库里的 MCP 配置。
如果需要 Photoshop / Illustrator / AutoCAD / ComfyUI 的可选桥接，再运行
.\bootstrap.ps1 -Profile standard；需要全部可选矢量依赖时运行
.\bootstrap.ps1 -Profile all。
```

在 macOS 或 Linux 上使用同一套 Python/MCP 档位时，运行：

```bash
bash ./bootstrap.sh --profile auto
```

`bootstrap.sh` 只创建仓库内的 `.venv`、安装公开 Python/MCP 依赖、生成本机 `.codex/config.toml` 并运行 safe MCP 自检。它不会安装 Homebrew、Xcode Command Line Tools、Rosetta 或桌面软件，也不会启动 Tauri；缺少可选前置条件时会明确提示，由用户手动决定是否安装。`standard` / `all` 仍使用与 Windows 相同的 Python extras，并可安装 Node bridge 依赖；桌面软件能力须另行验证。

为避免覆盖用户 MCP 设置，若现有 `.codex/config.toml` 非法，或 managed block 外已经定义 Starbridge MCP server / 冲突的 `mcp_servers` 结构，脚本会停止且不改写原文件；包含换行等控制字符的仓库路径也会被拒绝。`.codex` 与 `.venv` 必须是仓库内的真实目录而非 symlink；已有 `.venv` 的 `sys.prefix`、关键子目录以及 sysconfig/pip 可写安装路径也必须留在当前仓库的 `.venv` 内。POSIX bootstrap 自身的 Python 版本探测、`.venv` 创建、配置 helper、pip 和安装后验证都使用 `-I` 并移除继承的 `PYTHON*` 注入来源；pip 还会禁用配置文件并移除可改变安装落点或额外输入输出的非网络 `PIP_*` 覆盖，同时保留代理、证书和索引等网络环境。迁移 Windows quickstart managed block 时只接受 PowerShell `Resolve-Path` 可产生的规范绝对 Windows 路径，并拒绝 `CON`、`NUL.txt`、`COM1`、`COM¹`、`CONIN$` 等 Win32 保留设备名路径段。

也可以在本机直接从链接安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-from-url.ps1 `
  -RepositoryUrl "https://github.com/jianbaorui07-dot/CreNexus.git"
```

`auto` 会创建隔离的 `.venv`、安装可复用的 Python/MCP 和无桌面矢量依赖、安装本地 Codex MCP 配置，并运行安全自检。检测到本机桌面软件线索时会自动选择 `standard`。`standard` 和 `all` 才会安装 Node 代理和更重的可选包。

版本协同采用“能力探针优先”：Photoshop、Illustrator、AutoCAD、Blender、ComfyUI 和剪映/CapCut 的版本号只作为协同信息，不作为正版校验或版本白名单。桌面软件本身仍须由用户自行安装并按其许可使用；本项目不绕过登录、授权或激活。

安装脚本不会递归扫描私有目录，不会上传素材，不会把真实路径、账号、token 或 Cookie 写入 Git。`.codex/config.toml` 和 `.venv` 只保存在本机并已被 Git 忽略。
