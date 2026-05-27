# StarBridge 同类先进项目对比

调研时间：2026-05-24；2026-05-27 追加公开 GitHub 页面复核。第三方源码只克隆到本机 `third_party_research/`，该目录已加入 `.gitignore`，不进入 GitHub。以下结论来自 README、LICENSE、`requirements.txt`、`package.json`、`pyproject.toml`、启动方式、MCP 配置、工具接口和安全边界的只读分析；没有安装全局依赖、没有登录账号、没有调用真实素材。

## 2026-05-27 公开项目复核结论

本次复核重点看四类成熟项目的 README 呈现方式和可运行入口：

| 项目 | 明显强项 | StarBridge 对应修正 |
| --- | --- | --- |
| `daobataotie/CAD-MCP` | 开头就列出 CAD 支持范围、依赖、配置和 MCP Inspector 命令 | 保持 CAD 离线 DXF 与真实 AutoCAD 控制分层，并在 README 增加更短的验证命令 |
| `contextform/freecad-mcp` | Quick Install、更新、卸载、故障排查都放在 README 一屏内 | StarBridge 先补“三分钟验证”和 npm 快捷命令；完整安装器暂不进入 MVP |
| `joenorton/comfyui-mcp-server` | Quick Start 把 ComfyUI 启动、server 启动和 test client 验证拆清楚 | 增加 `comfy:workflow:validate`，先验证 workflow，不直接提交生成任务 |
| `artokun/comfyui-mcp` | 工具数量、插件/命令/技能清单和自动发现能力很完整 | 增加 `starbridge.tools` 能力清单，但保留 safe-only 过滤，避免工具过宽 |

复核后的判断：本仓库不应该追求“工具数量多”，而应该把中文导航、只读验证、能力注册表、安全边界和渐进式写入动作做扎实。相比成熟项目，本仓库当前最大缺口仍是完整 MCP stdio server、客户端配置样例、job/asset 生命周期和安装/故障排查文档。

## 对比表

| 项目名称 | 对应软件 | 技术路线 | 是否支持 MCP | 是否适合 Codex 调用 | 安装复杂度 | Windows 兼容性 | 可借鉴点 | 不能直接使用的风险 | 许可证风险 | 建议迁移优先级 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `loonghao/photoshop-python-api-mcp-server` | Photoshop | Python + `photoshop-python-api` + Windows COM + MCP stdio | 是 | 适合，Windows-only 定位清楚 | 中：Python 3.10+、Photoshop、COM、`uvx`/pip | 明确 Windows-only | Python 工具注册、session/document/layer 工具拆分、`PS_VERSION` 环境变量 | 依赖 Photoshop COM 和本机授权；工具能力大于本仓库当前安全边界 | MIT，风险低 | P0 |
| `alisaitteke/photoshop-mcp` | Photoshop | TypeScript/Node MCP + ExtendScript/batchPlay + Windows/macOS executor + 本地 UI | 是 | 适合借鉴架构，直接引入较重 | 中高：Node 18+、构建、Photoshop、可选本地 AI provider key | README 标注 Windows/macOS | 工具 registry、平台 detector/executor 分层、工具调用卡片、安全限制 UI | UI 会存本地 API key；示例提示含保存到桌面等个人路径习惯，需重写安全示例 | MIT，风险低 | P1 |
| `00bx/00bx-photoshop-mcp` | Photoshop/Adobe 多软件 | UXP 插件 + socket proxy + Python MCP + batchPlay，大量工具和 skills | 是 | 可借鉴工具目录和 UXP 通信，不宜直接集成 | 高：全局 npm、安装脚本、UXP Developer Tool、proxy、venv | UXP/Node/Python 混合，Windows 需实测 | UXP socket 桥、batchPlay 全量动作、技能按需加载 | 安装会写用户目录；工具过多，安全审计成本高；`package.json` 标 MIT 但仓库 LICENSE 为 Apache 文本，需核对 | 许可证标注不一致，迁移前需确认 | P2 |
| `ie3jp/illustrator-mcp-server` | Illustrator | TypeScript/Node MCP + JSX + macOS AppleScript / Windows PowerShell COM executor | 是 | 很适合借鉴，工具边界成熟 | 中：Node 20+、Illustrator CC 2024+、npx 或 MCPB | README 标注 macOS/Windows，Windows 硬件测试有保留说明 | 读/改/导出工具分层、print preflight、坐标系自动检测、临时 JSX/参数/result 文件模式 | 直接执行 modify/export 有客户稿风险；需先落地只读 status/document_info | MIT，风险低 | P0 |
| `krVatsal/illustrator-mcp` | Illustrator | Python MCP + ExtendScript + Windows COM/macOS osascript + screenshot | 是 | 适合做轻量 Python 参考 | 中：Python 3.12+、pywin32、Illustrator | README 标注 Windows/macOS | 简单 stdio server、跨平台脚本发送、prompt helper 工具 | 项目偏 prompt demo；许可证文件未在根目录明显出现，需确认后再借代码 | 许可证不清晰，暂不复制源码 | P2 |
| `ahujasid/blender-mcp` | Blender | Blender addon 内 socket server + Python MCP server | 是 | 适合借鉴运行模型，但要收紧任意 Python 执行 | 中：Blender 3+、Python 3.10+、uv、安装 addon | 跨平台，Windows 安装说明明确 | Blender addon + MCP 双进程通信、场景检查、截图、材质/对象工具 | 支持在 Blender 内执行任意 Python，安全边界必须重写；还含外部资产/API/telemetry 能力 | MIT，风险低 | P1 |
| `puran-water/autocad-mcp` | AutoCAD / AutoCAD LT | Python MCP + File IPC + AutoLISP dispatcher + ezdxf headless backend | 是 | 很适合 Codex，尤其 headless DXF fallback | 中：uv、Python、AutoCAD LT 2024+ 可选 LISP；headless 可无 AutoCAD | File IPC 要 Windows 原生 Python；ezdxf 跨平台 | 双 backend、8 个 consolidated tools、AutoLISP dispatcher、无 AutoCAD 时仍可 DXF | 需要用户手动 APPLOAD；真实 DWG 操作风险高 | MIT，风险低 | P0 |
| `AnCode666/multiCAD-mcp` | AutoCAD/ZWCAD/GstarCAD/BricsCAD | Python FastMCP + Windows COM + adapter/mixin + dashboard | 是 | 适合借鉴 CAD 统一 adapter 架构 | 中高：uv、pywin32、CAD 软件、FastMCP | Windows-only，COM 依赖明确 | 7 个 unified tools 聚合 50+ 命令、adapter manager、diagnostics、日志 | 默认输出目录示例和 dashboard/log 需脱敏；直接控制 CAD 需人工确认 | Apache-2.0，兼容但需保留声明 | P1 |
| `artokun/comfyui-mcp` | ComfyUI | TypeScript/Node MCP + ComfyUI client + Claude Code plugin/skills/agents/hooks | 是 | 适合借鉴插件化和命令体系，直接引入偏重 | 中高：Node 22+、npm、ComfyUI、可选模型下载/token | README 标注 macOS/Linux/Windows | workflow 执行、可视化、模型/节点发现、skills/commands/agents 组合 | 自动查找/下载模型和输出图像管理会触碰本仓库隐私边界 | MIT，风险低 | P1 |
| `IO-AtelierTech/comfyui-mcp` | ComfyUI | Python MCP + Pydantic settings + schema validation + workflow layout | 是 | 很适合借鉴 Python 工具分层 | 中：uvx/uv、ComfyUI、workflow env | 跨平台，依赖本机/远程 ComfyUI | system/discovery/workflow/execution 工具拆分、API/UI workflow 区分、workflow 校验 | 示例 env 有真实路径占位，接入时必须统一用 StarBridge 占位和脱敏 | MIT，风险低 | P0 |
| `joenorton/comfyui-mcp-server` | ComfyUI | Python MCP streamable HTTP + asset/job/workflow managers | 是 | 适合借鉴状态化作业和 asset identity | 中：pip、ComfyUI、HTTP server | 跨平台，localhost 默认 | streamable HTTP、job polling/cancel、asset registry、publish 管理 | 资产发布和输出目录管理容易泄露项目路径/生成图；asset session 生命周期需文档化 | Apache-2.0，兼容但需保留声明 | P1 |
| `sun-guannan/VectCutAPI` | 剪映/CapCut | Python/FastAPI + draft JSON + MCP server + pyJianYingDraft | 是 | 适合研究草稿桥，不宜直接纳入 | 中高：Python、FFmpeg、剪映/CapCut、可选云/API | README 提到 Windows venv；实际需本机验证 | draft create/save、字幕/音频/图片/特效工具、MCP 文档 | 项目含云 API、下载、OSS、草稿写入；真实素材和账号边界复杂 | LICENSE 为 Apache 文本但 pyproject classifier 写 MIT，需核对 | P2 |
| `Hommy-master/capcut-mate` | 剪映/CapCut | FastAPI + Pydantic + 草稿/素材/导出 + 可选 Windows UI 自动化依赖 | 否，偏 REST/API | 可由 Codex 调 REST，但不是 MCP-first | 高：Python 3.11+、uv、FastAPI、可选 pyautogui/uiautomation | Windows extras 明确 | 草稿管理、素材添加、API 文档、本地服务化 | 含云渲染/导出/下载/账号场景，生产边界不适合本仓库 MVP | MIT，风险低 | P2 |
| `xuliang2024/cutcli-cookbook` | 剪映/CapCut | cutcli CLI 案例库 + 模板 + prompts + 文档站 | 非 MCP server，但面向 MCP agent/Claude Code/Cursor | 适合 Codex 用 CLI 思路驱动 | 中：需安装外部 cutcli，部分命令可能涉及云 API key | README 说明剪映/CapCut 草稿可打开，Windows 需实测 | “生成可二次编辑草稿”的产品边界、案例模板、AI agent prompt | cutcli 是外部二进制/服务，云渲染需要 API key；不能把用户草稿直接提交 | MIT，风险低 | P1 |

## 迁移结论

P0 先做四件事：

1. 借鉴 `puran-water/autocad-mcp` 的 headless DXF fallback 思路，把 CAD 能力分为“可离线生成”和“需要 AutoCAD 控制”。
2. 借鉴 `IO-AtelierTech/comfyui-mcp` 的 system/discovery/workflow/execution 分层，但本仓库先只实现 status/probe。
3. 借鉴 `loonghao/photoshop-python-api-mcp-server` 的 Windows COM 明确边界，把 Photoshop 先做 session/document status，再做小动作。
4. 借鉴 `ie3jp/illustrator-mcp-server` 的 JSX runner 与 preflight 工具分类，但本仓库先保留只读探针。

P1 用于架构参考：

- `alisaitteke/photoshop-mcp`：平台 detector/executor、工具 registry、本地 UI 的审计卡片。
- `ahujasid/blender-mcp`：Blender addon 与 MCP server 分离，但必须禁用或隔离任意代码执行。
- `AnCode666/multiCAD-mcp`：多 CAD adapter/mixin 结构和 diagnostics。
- `artokun/comfyui-mcp`、`joenorton/comfyui-mcp-server`：ComfyUI 作业、资产、workflow 生命周期。
- `xuliang2024/cutcli-cookbook`：剪映/CapCut “草稿桥”而不是桌面自动点击。

P2/P3 暂不直接迁移源码，只保留调研：

- 许可证或安装路径不清晰、工具过宽、会写用户目录、含云账号/API key、或需要 UXP/全局安装的项目，都不进入 StarBridge MVP。
- 本轮没有项目被标为 P3；但涉及账号登录、云渲染、批量下载、付费能力绕过或自动发布的子功能，一律按 P3 处理。
