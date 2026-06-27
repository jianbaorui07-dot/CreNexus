# Codex Computer Use on Windows

这份文档说明 Codex Computer Use 在本仓库里的定位。它是 GUI 通道，负责看见和操作 Windows 桌面软件；StarBridge MCP 是结构化工具通道，负责把稳定动作做成可复现、可测试、可脱敏的工具。

## 适合 Computer Use 的任务

- 查看真实桌面窗口、菜单、面板、画布、时间线或对话框状态。
- 复现用户在 Photoshop、Illustrator、AutoCAD、Blender、ComfyUI GUI、剪映 / CapCut 里看到的问题。
- 进行低风险的点击、滚动、快捷键、拖拽和文本输入，用来确认 UI 路径是否存在。
- 截图留证，配合脱敏报告说明“窗口里发生了什么”。
- 在 MCP 工具失败时，观察软件是否弹出授权、插件、文件锁定、崩溃或兼容性提示。

Computer Use 不适合作为生产批处理的唯一执行方式。凡是需要长期稳定、可测试、可重复、可 CI 验证的动作，都应该沉淀到 StarBridge MCP tools、CLI 或参数化脚本里。

## 仍应使用 StarBridge MCP 的任务

- 读取桥状态、工具能力和环境摘要。
- 校验 ComfyUI workflow、CAD plan、DXF 输出计划等结构化输入。
- 运行只读 probe、路径脱敏、发布前体检和安全检查。
- 执行可审计的参数化导出、dry-run、sandboxed output 写入。
- 给 Codex / Cursor / Claude Code 提供稳定的 `tools/list` / `tools/call` 接口。
- 在 CI 或本机测试里复现同一条命令，而不是依赖某次 GUI 点击。

## 双通道工作流

| 软件 | Computer Use GUI 通道 | StarBridge MCP / structured tools 通道 | 推荐分工 |
| --- | --- | --- | --- |
| Photoshop | 查看文档、图层面板、菜单状态；复现主体选择、导出面板或插件异常 | `photoshop.session_info`、参数化文档信息、受保护导出脚本 | GUI 负责观察和复现，MCP 负责只读摘要和可确认写入 |
| Illustrator | 查看画板、链接资源、Image Trace 面板、导出对话框 | `illustrator.document_info`、后续白名单 JSX、导出 preflight | GUI 负责确认 UI 行为，MCP 负责参数化读取和导出 |
| AutoCAD | 查看 DWG/DXF 打开状态、命令行提示、图层和视图问题 | `cad_autocad.environment_probe`、`autocad_dxf.*`、AutoCAD MCP 子项目 | GUI 负责问题复现，MCP 优先做离线 DXF plan 和结构化 CAD 操作 |
| ComfyUI | 查看节点图、队列、浏览器 UI 报错、预览图状态 | `comfyui.system_probe`、`comfyui.workflow_validate`、`comfy.workflow_lifecycle_summary`、workflow JSON | GUI 负责观察节点和错误，MCP 负责 API probe、workflow 校验和脱敏 lifecycle 摘要 |
| Blender | 查看视口、Outliner、材质、渲染窗口、插件状态 | `blender.environment_probe`、后续 scene 摘要和安全渲染脚本 | GUI 负责视觉确认，MCP 负责环境检查和结构化 scene 操作 |
| CapCut / Jianying | 查看时间线、模板、字幕、导出窗口和授权提示 | `jianying_capcut.draft_probe`、后续只读草稿结构摘要 | GUI 只做观察和低风险复现，MCP 不读取私有草稿内容 |

## 安全分级

| 等级 | 名称 | 允许动作 | 例子 |
| --- | --- | --- | --- |
| L0 | read-only | 只读观察、截图、状态检查、脱敏摘要 | 查看窗口、运行 `bridge_status.py --json --redact-paths --soft-exit` |
| L1 | local safe | 本机安全动作，不上传、不删除、不触碰客户素材，输出在忽略目录或 dry-run | 生成 CAD plan、校验 workflow、创建测试画板计划 |
| L2 | confirmed write | 写入或导出前需要用户明确确认，路径必须由参数传入并限制在安全目录 | 导出 PNG/DXF/SVG、创建测试草稿、保存本机报告 |
| L3 | blocked | 默认阻止，不能由 Codex 自动完成 | 账号、密码、验证码、支付、上传客户素材、删除文件、修改系统安全设置 |

## 禁止自动操作

以下动作禁止 Codex 通过 Computer Use 或 MCP 自动完成，除非另有人工接管流程；其中账号、密码、验证码、支付和系统安全设置不应由 Codex 代操作：

- 输入、保存或修改账号、密码、验证码、OTP、API key、OAuth token、Cookie。
- 创建、登录、切换或授权第三方账号。
- 发起支付、订阅、购买、退款或保存支付方式。
- 上传客户素材、客户图纸、商业 PSD / AI / DWG / `.blend` / 视频草稿或私有模型。
- 删除本机文件、云端文件、邮件、日历、草稿、素材库或项目输出。
- 修改 Windows 安全设置、浏览器安全设置、隐私权限、防病毒配置或系统密码。
- 绕过安全提示、验证码、付费墙、网页登录限制或软件授权检查。

## 验证命令

Computer Use 产生的 GUI 观察结果应尽量配套一条可复现命令。常用验证入口：

```powershell
npm.cmd test
npm.cmd run preflight
python examples\bridge_status.py --json --redact-paths --soft-exit
```

如果 GUI 里看到异常，优先把它整理成 MCP 工具的输入、失败输出、脱敏截图描述和可复现命令，而不是只保留一次点击过程。
