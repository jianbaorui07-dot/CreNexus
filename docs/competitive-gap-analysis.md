# 同类创意软件 MCP 项目差距分析

更新时间：2026-07-13。

这份分析只比较公开仓库已经展示的架构与接口，不复制第三方源码，也不把外部项目能力写成 StarBridge 已验证能力。

## 参考项目与先进点

| 一手来源 | 值得吸收的能力 | StarBridge 当前差距 |
| --- | --- | --- |
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) | Blender addon 与 MCP server 双向 socket；场景检查、对象/材质控制、viewport screenshot | 已有环境探针、scene plan 和 reference reconstruction plan；缺少受控 live sandbox adapter 与视觉回看闭环 |
| [sandraschi/blender-mcp](https://github.com/sandraschi/blender-mcp) | 按 scene/object/render 等域组织高层工具，并提供 dashboard/telemetry | 已有统一 registry 和前端原型；缺少跨 bridge 的实时 operation telemetry 与状态差异展示 |
| [artokun/comfyui-mcp](https://github.com/artokun/comfyui-mcp) | queue 默认省略 workflow、直接读权威深度、WebSocket 单调进度与 stalled/backlog 检测 | 已有脱敏 queue snapshot 和数值进度契约；仍缺 live WebSocket、stall 时钟与恢复通知 |
| [IO-AtelierTech/comfyui-mcp](https://github.com/IO-AtelierTech/comfyui-mcp) | queue/history/interrupt/object_info 等完整作业控制面 | 已实现只读 loopback queue snapshot；受控 cancel 与 history 摘要仍未开放 |
| [alisaitteke/photoshop-mcp](https://github.com/alisaitteke/photoshop-mcp) | 操作后返回 document/layer context，降低模型丢失软件状态的概率 | 已有 `ps.get_state` / `ps.get_preview`；缺少所有 recipe 共用的 before/after state delta |
| [MCP 官方 TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/docs/server.md) | `outputSchema`、structured result、sampling、elicitation 与实验性 Tasks | 当前 stdio server 支持同步 `tools/call` 和 `structuredContent`；Tasks、进度通知尚未实现 |
| [MCP 官方规范仓库](https://github.com/modelcontextprotocol/modelcontextprotocol) | 协议 schema、能力协商与持续演进的扩展机制 | 已声明 tools/resources/prompts；尚未实现任务、进度和 UI extension 能力协商 |

## 迭代优先级

| 优先级 | 增强项 | 原因 | 当前状态 |
| --- | --- | --- | --- |
| P0 | ComfyUI workflow → Mermaid + 脱敏结构摘要 | 纯内存、跨平台，立刻提升 Codex 对复杂 graph 的理解 | 已实现 `comfy.workflow_visualize` |
| P1 | 统一 operation context envelope | 每次 recipe 返回 before/after state、warnings、evidence 引用 | 已实现 `starbridge.operation_context`，见 [统一 Operation Context Envelope](operation-context-envelope.md) |
| P1 | 只读 queue snapshot + 结构化进度 | 支撑长任务监控，不需要先开放生成或写入 | 已实现 `comfyui.queue_snapshot` v1：默认 plan-only、live loopback `/queue`、逻辑 job ID、backpressure 与单调数值进度；真实 WebSocket 仍待实现 |
| P2 | MCP Tasks / progress capability | 支持 call-now/fetch-later 和断线恢复 | 待客户端兼容矩阵与协议测试 |
| P2 | Blender/Adobe live sandbox adapter | 才能形成真实软件控制闭环 | 需要本机授权软件、显式确认与独立安全审查 |
| P3 | MCP App dashboard | 让状态、graph、证据和确认门可交互 | 需要先稳定 P1/P2 数据协议 |

## 采用原则

- 优先复制接口思想，不复制第三方代码。
- 不引入任意 Python、JSX、PowerShell 或任意路径执行。
- 新能力先稳定纯内存 schema 和测试，再连接本地软件。
- 文档能力描述必须与可复查验证证据一致。
