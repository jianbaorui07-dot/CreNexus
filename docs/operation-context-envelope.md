# 统一 Operation Context Envelope

StarBridge 的 recipe 已能返回计划、风险等级、质量门和 EvidenceManifest，但此前没有统一描述“一次操作前后软件状态发生了什么变化”。这会让 Codex 在多步操作中反复读取状态，也容易在失败后丢失当前上下文。

参考项目：

- [alisaitteke/photoshop-mcp](https://github.com/alisaitteke/photoshop-mcp) 会在操作后返回文档、活动图层、选择状态和操作结果。
- [MCP 2025-06-18 schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-06-18/schema.ts) 支持为 tool 声明 `outputSchema`，并通过 `structuredContent` 返回结构化结果。

StarBridge 不复制第三方实现，也不开放任意脚本。本协议只吸收“操作后附带可预测上下文”的接口模式。

## v1 契约

MCP tool：`starbridge.operation_context`

输入：

| 字段 | 说明 |
| --- | --- |
| `bridge` | 软件桥标识，例如 `photoshop`、`illustrator`、`blender`、`comfyui` |
| `action` | 安全的操作标识，不接受路径或自由脚本 |
| `phase` | `planned`、`before`、`after`、`completed` 或 `failed` |
| `before_state` | 操作前的白名单指标 |
| `after_state` | 操作后的白名单指标 |
| `warnings` | 可选警告；返回前统一脱敏 |
| `evidence_refs` | `manifest::...`、`job::...`、`recipe::...` 或 `transaction::...` 逻辑引用，不接受文件路径 |
| `parent_context_id` | 可选上一条 `ctx_...`，用于串联多步操作 |

允许的状态字段只包含计数、尺寸、进度、布尔状态和受控标签：

```text
state_revision, connected, document_open, document_width, document_height,
canvas_width, canvas_height, resolution, layer_count, selection_count,
artboard_count, object_count, material_count, frame_count, track_count,
queue_pending, queue_running, queue_completed, queue_failed, progress,
duration_ms, status, active_item_type, color_mode
```

输出固定包含：

- `schema_version=starbridge.operation-context.v1`
- 可复现的 `context_id`
- 可选 `parent_context_id`
- `before` / `after` 安全快照
- `added` / `removed` / `changed` / `unchanged_fields` 差异
- `warnings`、`evidence_refs`、`next_steps`
- 明确的只读安全声明

## 安全边界

- 只处理调用方传入的内联摘要，不访问文件、网络或桌面软件。
- 不允许未知状态字段，避免把文档名、图层名、prompt、模型名或素材内容混入上下文。
- 状态标签不得包含路径、token、Cookie、OAuth、PSD、AI、DWG、模型或草稿线索。
- evidence 只使用逻辑 ID，不接收 manifest 文件路径。
- warning 会经过 StarBridge sanitizer；是否发生脱敏会在结果中标记。
- tool 本身永远只读，即使它描述的是一次已确认写入后的状态。

## Recipe 接入

`starbridge.recipe_plan` 为每个跨软件 recipe 返回相同的 `operation_context` 契约，要求在首个主要动作前、主要动作后和失败后采集安全摘要。`starbridge.recipe_evidence` 会记录该 schema 版本，但不会自动读取任何软件状态。

示例：

```json
{
  "name": "starbridge.operation_context",
  "arguments": {
    "bridge": "photoshop",
    "action": "recipe_preview",
    "phase": "completed",
    "before_state": {"document_open": true, "layer_count": 2, "progress": 0},
    "after_state": {"document_open": true, "layer_count": 3, "progress": 100},
    "evidence_refs": ["recipe::photoshop_preview_export"]
  }
}
```

这不是实时 Photoshop/Blender adapter，也不是 MCP Tasks 实现；它先把跨软件状态回传格式稳定下来，为后续 queue snapshot、实时进度和可恢复任务提供公共数据层。
