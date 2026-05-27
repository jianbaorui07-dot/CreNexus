# StarBridge 工具能力路线图

本文件只规划 StarBridge 后续工具接口，不代表当前已经实现所有动作。当前已稳定的是统一 `status` / `probe` 状态入口；涉及打开文件、导出、执行脚本的能力必须在安全边界和用户确认策略清楚后再实现。

## 统一工具分层

| 工具能力 | 目标 | 默认安全策略 |
| --- | --- | --- |
| `status` | 返回 bridge 是否可用、缺少什么配置、下一步怎么做 | 只读，不触碰用户素材 |
| `probe` | 做更具体的本机连接探测，例如 HTTP、COM、可执行文件、草稿目录 | 只读，不打开私有工程 |
| `open_file` | 打开用户显式指定的文件 | 只接受参数传入路径，不内置个人路径 |
| `read_document_info` | 读取当前文档、画板、图层、尺寸、颜色模式等摘要 | 不输出真实素材路径，不读取客户内容细节 |
| `export_result` | 导出 PNG/SVG/PDF/DXF/视频草稿等结果 | 只导出到参数指定目录或本机忽略目录 |
| `run_script` | 执行小型参数化自动化脚本 | 默认关闭；必须限制脚本来源、参数和输出目录 |

所有 status/probe JSON 输出必须经过 StarBridge sanitizer。普通 `--json` 不因本机软件未安装或未启动而失败；`--strict` 才用于失败退出码。当前 MCP stdio server 已把各桥的安全探针挂成直接 tools，写入类动作仍然需要默认 dry-run 或显式确认。

## Bridge 路线图

| Bridge | status | probe | open_file | read_document_info | export_result | run_script |
| --- | --- | --- | --- | --- | --- | --- |
| `comfyui` | 已有：检查 API 地址和基础节点 | 已有：读取 `/system_stats`、`/object_info` | P2：只允许上传/引用用户显式提供的输入 | P1：读取 workflow 元信息和节点依赖 | P1：提交 workflow 后返回 prompt/job 摘要，不提交图片 | P2：只运行仓库内公开 workflow，不执行任意 Python |
| `photoshop` | 已有：检查 pywin32、`PHOTOSHOP_EXE`、COM 线索 | 已有：可选 COM 探测 | P1：只打开用户显式传入图片/PSD | P0：读取当前文档尺寸、模式、图层数量 | P1：参数化导出 PNG，不写默认桌面路径 | P2：只允许仓库内 PowerShell/JSX 动作白名单 |
| `illustrator` | 已有：检查 pywin32、`ILLUSTRATOR_EXE`、COM 线索 | 已有：可选 COM 探测 | P1：只打开用户显式传入 `.ai`/SVG/PDF | P0：读取画板、颜色模式、文字和链接摘要 | P1：导出 SVG/PDF/PNG 到指定目录 | P2：只允许白名单 JSX，不执行任意脚本 |
| `blender` | 已有：检查 `BLENDER_EXE` 和可选 MCP 目录 | 已有：可选 `blender --version` | P2：只打开用户显式传入 `.blend` | P1：读取 scene/object/camera/render 摘要 | P1：渲染到本机忽略目录 | P3：任意 Python 风险高，先只允许仓库内脚本 |
| `autocad` | 已有：检查 MCP 子项目、`AUTOCAD_EXE`、win32com | 已有：AutoCAD 可执行文件/COM 线索 | P2：只打开用户显式传入 DWG/DXF | P1：读取图层、实体数量、单位摘要 | P0：离线 DXF 生成优先；真实 CAD 导出需确认 | P2：只允许参数化 CAD 动作，不执行任意命令 |
| `jianying_capcut` | 已有：检查可执行文件和草稿目录环境变量 | 已有：只读配置探测 | P3：暂不自动打开草稿 | P1：只读草稿结构摘要，不输出素材路径 | P2：生成安全测试草稿；视频导出由用户手动确认 | P3：不做桌面自动点击和账号相关脚本 |

## 已挂入 MCP stdio 的工具

| MCP tool | Bridge | 安全边界 |
| --- | --- | --- |
| `starbridge.status` | all | 统一状态摘要，只读 |
| `starbridge.probe` | all | 单桥只读探针 |
| `starbridge.tools` | all | 能力注册表 |
| `comfyui.system_probe` | ComfyUI | 只读 `/system_stats` 和 `/object_info`，不提交 prompt |
| `comfyui.workflow_validate` | ComfyUI | 只读 workflow JSON 校验 |
| `blender.environment_probe` | Blender | 不打开 `.blend`，不运行 Python |
| `cad_autocad.environment_probe` | AutoCAD / CAD | 不打开 DWG/DXF，不控制 CAD |
| `photoshop.session_info` | Photoshop | 只读 COM/session 线索，不保存导出 |
| `illustrator.document_info` | Illustrator | 只读 COM/session 线索，不打开私有 `.ai` |
| `jianying_capcut.draft_probe` | 剪映 / CapCut | 不读取草稿内容，不导出视频 |
| `autocad_dxf.status` | DXF | 离线 DXF bridge 状态 |
| `autocad_dxf.validate_cad_plan` | DXF | 只校验传入 JSON |
| `autocad_dxf.create_dxf_plan` | DXF | 生成可审查 plan，不写文件 |
| `autocad_dxf.summarize_plan` | DXF | 汇总 plan，不写文件 |
| `autocad_dxf.write_dxf` | DXF | 默认 dry-run；真实写入需 `confirm_write=true` 且限制在 `examples/cad/output` |

## 优先级

P0：

- 稳定 `starbridge.status` / `starbridge.probe`。
- Photoshop / Illustrator 当前文档只读信息。
- AutoCAD 离线 DXF 生成和状态分层。

P1：

- ComfyUI workflow 校验和 job 摘要。
- Blender scene 摘要与安全渲染探针。
- 剪映 / CapCut 草稿结构只读摘要。

P2：

- 文件打开、导出、白名单脚本执行。
- 多软件 adapter 与统一错误码。

P3：

- 任意脚本执行。
- 自动登录、账号、云端发布、付费能力或绕过授权相关功能。
