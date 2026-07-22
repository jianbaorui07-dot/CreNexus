# 安装和发布路径

这份文档把 CreNexus 从“能跑的工程仓库”整理成更像产品的安装入口和发布路线。当前仓库仍是 `v0.1-alpha`，下面的 PyPI、npm 和 MCP registry 步骤是发布路径，不代表已经正式发布。

## 一键本机检查

只读检查当前工作站是否具备基础工具、环境变量和可选桌面软件线索：

```powershell
npm.cmd run install:check
npm.cmd run install:check:json
```

## 一键 bootstrap

首次克隆后可以用一条命令创建 `.venv`、安装 dev 依赖并把当前包以 editable 模式安装到本机：

```powershell
npm.cmd run install:bootstrap:dry-run
npm.cmd run install:bootstrap
```

`install:bootstrap:dry-run` 只输出计划，不写入虚拟环境。`install:bootstrap` 会写入本机 `.venv`，该目录被 `.gitignore` 忽略。

## 给 Codex 的 3 分钟安装

首次把仓库链接交给 Codex 时，Windows 使用项目根目录的 `bootstrap.ps1`：

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Profile auto
```

它会创建隔离环境、按档位安装依赖、生成项目级 `.codex/config.toml`，并执行 Python 包、版本协同器和 safe MCP tools 自检。`auto` 默认走轻量的无桌面路径；检测到桌面软件线索时升级到 `standard`。需要更完整的可选依赖时使用 `-Profile standard` 或 `-Profile all`。

macOS / Linux 使用仓库根目录的 `bootstrap.sh`：

```bash
bash ./bootstrap.sh --profile auto
```

它保持 `auto` / `core` / `standard` / `all` 的 Python extras 语义，使用 `.venv/bin/python` 和动态 POSIX 路径生成同一份安全 MCP 配置。它只操作当前仓库的 `.venv`、可选 Node bridge 依赖和被忽略的 `.codex/config.toml`；不会自动安装 Homebrew、Xcode Command Line Tools、Rosetta 或桌面软件，也不接管 Tauri 桌面运行链。缺少这些可选前置条件时会提示用户手动处理，核心 Python/MCP 路径仍可独立验证。

如果只有 Git URL，也可以在任意目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-from-url.ps1 `
  -RepositoryUrl "https://github.com/jianbaorui07-dot/CreNexus.git"
```

安装脚本按能力探针适配版本，不以正版校验或固定版本白名单阻断 Photoshop、Illustrator、AutoCAD、Blender、ComfyUI 和剪映/CapCut；桌面软件授权、登录和激活仍由用户自行负责，脚本不会绕过这些机制。

## MCP 客户端配置

本地 MCP stdio server 入口：

```powershell
python -m starbridge_mcp.mcp_server
```

客户端配置可以使用下面的 command / args：

```json
{
  "command": "python",
  "args": ["-m", "starbridge_mcp.mcp_server"]
}
```

MCP registry 示例位于 [docs/mcp-registry-entry.example.json](mcp-registry-entry.example.json)，可用下面的命令检查 JSON 形状：

```powershell
npm.cmd run mcp:registry:preview
```

## PyPI 发布路径

当前 `pyproject.toml` 已声明包名、入口点和可选依赖。正式发 PyPI 前至少需要：

1. 确认 `VERSION`、`pyproject.toml` 和 release note 版本一致。
2. 运行 `python -m unittest discover -s tests`、`python scripts\security_check.py` 和 `python scripts\starbridge_preflight.py --markdown`。
3. 构建 wheel / sdist，并在干净虚拟环境中安装 smoke test。
4. 确认包内不包含模型、图片、PSD、AI、DWG、视频、私有路径或本机缓存。

本地元数据检查：

```powershell
npm.cmd run package:python:check
```

正式发布时再使用 `python -m build` 和 `twine upload`。这两个步骤需要维护者手动配置 PyPI token，不写入仓库。

## npm 发布路径

根目录 `package.json` 当前主要用于本地快捷命令，`private=true` 表示不会误发 npm。若未来要发布 npm 包，建议新建一个只包含 CLI wrapper 的子包，而不是把整个仓库直接发布。

推荐路线：

1. 保持根目录 `package.json` 作为开发命令入口。
2. 新增 `packages/starbridge-cli/`，只包装 `python -m starbridge_mcp.mcp_server` 和安装检查。
3. npm 包只声明 CLI、README 和最小 metadata，不打包本机输出、示例生成物或桌面软件资产。
4. 发布前跑 `npm pack --dry-run`，人工检查文件清单。

## 发布前产品化清单

- README 第一屏能说明项目定位、能力边界和最短运行命令。
- `install:check` 可在没有 Adobe、AutoCAD、Blender、ComfyUI 或 CapCut 的机器上 soft-exit。
- MCP registry 示例只包含 stdio 入口、能力摘要和安全说明，不包含真实路径。
- PyPI / npm 发布动作需要维护者手动 token，不自动登录、不自动上传。
- 可视化 demo 只展示公开能力矩阵和验证命令，不包含私有素材截图。
- 新增 `ps.get_preview` / `ps.get_state` 后更新 capability matrix 和示例。
- Recipes (remove_background 等) 和 Action Plan 模式已添加，保持 dry_run + manifest 安全。
- 运行 `python -m ruff check . && python scripts/starbridge_preflight.py` 再发布。
- 考虑 GitHub release: 用 `gh release create` 或 .github/workflows/release.yml，附带 CHANGELOG 片段和 artifacts。
- 发布 workflow 触发于 tag v*，生成 release notes，包含 wheel/tar.gz。
- 手动启用 PyPI 上传部分，使用 secrets。
