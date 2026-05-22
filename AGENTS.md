# Agent Instructions

这个仓库现在只作为 **Codex 接入各类本地软件** 的公开协作仓库。优先保持内容精简、中文说明清楚、示例可运行，不再把 unrelated demo、报告脚本、素材图片和临时输出发到 GitHub。

## 发布范围

- `docs/`：Codex 接入软件的协议、路线图和中文用途索引。
- `examples/`：公开安全的桥接状态检查和 ComfyUI API 示例。
- `examples/photoshop_bridge/`：Photoshop 本地桥示例，只能包含通用参数化脚本，不能包含本机路径或素材信息。
- `cad-mcp-autocad/`：AutoCAD MCP 子项目。修改前先读本目录 README 和 `requirements.txt`。
- `scripts/`：只保留与 AutoCAD/CAD 自动化直接相关的脚本。
- `AUTOCAD_MCP_SETUP.md`：AutoCAD MCP 本地配置记录。
- `package.json`：本地桥接检查快捷命令。

## 不发布范围

以下内容可以留在本机，但不要提交到 GitHub：

- `src/`、`virtual-pet/`、`overtime-analysis-deck/` 等历史 demo 或非接入项目。
- 报告生成脚本、样式参考文档、图片素材、PPT 工作区。
- `output/`、`scratch/`、`docx_render_check/`、`.codex_video_frames/`、`.codex_video_deps/`、`node_modules/`、`__pycache__/`。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成图片。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存。
- CAD 客户图纸、商业 DWG、授权文件和真实项目输出。
- Photoshop 安装路径、Creative Cloud 缓存、PSD 私有工程、商业字体、商业笔刷、购买素材、源图路径和导出结果。
- 密码、token、Cookie、OAuth 缓存、浏览器资料、支付信息。

## 修改规则

- 优先做小而清晰的变更，不做无关重构。
- 说明文字以中文为主；命令、路径、API、MCP、workflow、prompt 等必要术语可以保留英文。
- 新增下载源码或安装包时，先放到本机下载收件箱；用 `STARBRIDGE_DOWNLOAD_INBOX` 在本地配置，不要把真实路径写进仓库。
- Photoshop 示例必须通过参数传入输入和输出路径；不要把个人路径、文件名、素材目录或桌面路径写成默认值。
- 修改 Python 脚本前先检查 imports、输入路径、输出路径和平台依赖。
- 修改 `cad-mcp-autocad/` 时，尽量把改动限制在该子项目内。
- 不要删除本机文件；如果只是清理 GitHub 发布范围，优先用 `git rm --cached` 让文件留在本地。
- 需要登录、订阅、验证码、OAuth、GitHub 授权或账号审批时，停下来让用户手动处理。

## 验证方式

- 总状态检查：

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
```

- ComfyUI 探针：

```powershell
python examples\comfy_bridge\comfy_probe.py
```

- AutoCAD MCP 测试：

```powershell
python scripts\test_autocad_mcp.py
```

注意：AutoCAD 自动化需要 Windows 和本机 AutoCAD。ComfyUI 相关脚本需要先启动本机 ComfyUI。
