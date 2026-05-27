# 第三方项目本机吸收计划

更新时间：2026-05-27。

本页记录把第三方创意软件 MCP / bridge 项目先拉到本机、再安全吸收到 StarBridge 的方式。第三方源码只放在 `third_party_research/`，该目录已被 `.gitignore` 忽略；公开仓库只提交抽象后的接口、中文说明、测试和安全边界。

## 已本机更新的参考项目

| 本机目录 | 参考方向 | 本轮吸收点 |
| --- | --- | --- |
| `third_party_research/autocad-mcp` | AutoCAD / DXF | 离线 DXF fallback、真实 CAD 控制与 headless export 分层 |
| `third_party_research/photoshop-python-api-mcp-server` | Photoshop | Windows COM 边界、session/document/layer 工具拆分 |
| `third_party_research/photoshop-mcp` | Photoshop | tool registry、平台 detector/executor 分层、安全提示 |
| `third_party_research/illustrator-mcp-server` | Illustrator | read / modify / export 工具分类、preflight 思路 |
| `third_party_research/IO-AtelierTech-comfyui-mcp` | ComfyUI | system / discovery / workflow / execution 分层 |
| `third_party_research/comfyui-mcp` | ComfyUI | 工具描述质量、插件/skills/hooks 目录组织、workflow 生命周期 |
| `third_party_research/blender-mcp` | Blender | Blender addon 与 MCP server 分离 |
| `third_party_research/multiCAD-mcp` | 多 CAD | adapter / diagnostics 思路 |
| `third_party_research/VectCutAPI` | 剪映 / CapCut | 草稿桥、REST/MCP 双入口研究 |

## 已吸收到本仓库的内容

本轮没有复制第三方源码，先新增 StarBridge 自己的工具能力注册表：

- `starbridge_mcp/core/tool_registry.py`
- `python -m starbridge_mcp.server tools --json`
- `python -m starbridge_mcp.server tools --json --safe-only`
- `python examples/comfy_bridge/validate_workflow.py --json`
- `npm.cmd run starbridge:tools`
- `npm.cmd run starbridge:tools:safe`
- `npm.cmd run comfy:workflow:validate`

能力注册表为每个 bridge 记录：

- `name`：未来 MCP tool 名称。
- `bridge`：所属软件桥。
- `maturity`：`implemented`、`experimental`、`planned` 或 `research`。
- `risk_level`：只读、受控本机写入、受控进程启动等。
- `side_effects`：是否会打开软件、访问 API、写文件。
- `safe_default`：是否适合作为默认可调用能力。
- `requires_confirmation`：是否必须先让用户确认。
- `source_projects`：只记录借鉴来源，不代表复制源码。

## 下一步迁移顺序

1. **CAD / AutoCAD**：继续把离线 `autocad_dxf` 做成稳定工具面，保持 `dry_run=True` 默认值，真实 AutoCAD 控制单独隔离。
2. **ComfyUI**：继续扩展只读 workflow validator，目前已能检查 API format、节点和连线引用，不提交生成任务。
3. **Photoshop**：把 `document_info.ps1` 的输出对齐到 StarBridge result schema，先做当前文档只读摘要。
4. **Illustrator**：实现只读 `document_info` / `preflight` 原型，不打开客户 `.ai` 文件。
5. **Blender**：只做固定模板 scene probe，不开放任意 Python 执行，不下载 Sketchfab / Poly Haven / 3D 资产。
6. **剪映 / CapCut**：继续只读草稿目录探针；写草稿或导出视频必须等许可、账号和隐私边界确认。

## 不迁移的内容

- 第三方项目里的真实安装路径、桌面路径、输出目录示例。
- 模型下载、CivitAI/HuggingFace token、云渲染、OSS 上传、账号登录逻辑。
- 任意 Python/JSX/ExtendScript 执行入口。
- 会自动打开客户 PSD、AI、DWG、草稿或导出真实结果的宽工具。
- 许可证不清晰或会写用户目录的安装脚本。
