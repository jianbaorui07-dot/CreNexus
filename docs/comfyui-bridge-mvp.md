# ComfyUI Bridge MVP

## 目标

ComfyUI bridge 的目标是让 StarBridge 能安全地检测、描述、验证和可控调用本地 ComfyUI 服务。它不是 ComfyUI 替代品，也不管理模型、LoRA、VAE、ControlNet 或 custom node。

## 当前已支持功能

- `status()`：检查 API 地址和 `/system_stats` 是否可达。
- `probe()`：读取 ComfyUI 系统状态，失败时返回结构化错误。
- `list_models()`：尝试从 `CheckpointLoaderSimple` 的 `object_info` 中读取 checkpoint 名称。
- `validate_workflow(workflow_json)`：只做基本 JSON 结构检查，不执行 workflow。
- `queue_workflow(workflow_json, dry_run=True)`：默认 dry-run，只验证不提交。

所有返回值使用统一 schema：

```json
{
  "ok": false,
  "bridge": "comfyui",
  "action": "status",
  "message": "...",
  "details": {},
  "warnings": [],
  "next_steps": []
}
```

## 默认 URL

默认 ComfyUI API 地址：

```text
http://127.0.0.1:8188
```

## 环境变量

| 环境变量 | 用途 |
| --- | --- |
| `STARBRIDGE_COMFYUI_URL` | 覆盖默认 API 地址 |
| `STARBRIDGE_COMFYUI_ALLOW_QUEUE` | 显式允许真实 queue；默认不允许 |

## dry_run 安全机制

`queue_workflow` 默认 `dry_run=True`。此时只会：

1. 解析 workflow。
2. 检查是否是非空 JSON object。
3. 检查是否存在节点和 `class_type` / `type`。
4. 返回 dry-run 结果。

不会调用 ComfyUI `/prompt`，不会生成图片，不会写输出文件。

真实提交必须同时满足：

- 调用方传入 `dry_run=False`。
- 环境变量 `STARBRIDGE_COMFYUI_ALLOW_QUEUE=true`。

## 如何检测本地 ComfyUI 是否启动

```powershell
python examples\comfyui\check_comfyui_status.py
```

或者运行只读 PowerShell 检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_comfyui_local.ps1
```

服务未启动时，bridge 会返回 `ok=false`、原因和下一步建议，而不是抛出未处理异常。

## 如何验证 workflow

```powershell
python examples\comfyui\validate_workflow.py
```

示例文件是 `examples/comfyui/sample_workflow_minimal.json`。它只包含占位 checkpoint 名称，不包含真实模型路径或用户素材路径。

## 为什么默认不直接 queue 任务

ComfyUI workflow 可能触发大型模型加载、长时间 GPU 任务、大量输出文件和 custom node 副作用。StarBridge 默认不提交真实任务，是为了避免：

- 误跑大型生成任务。
- 写入大量本地输出。
- 依赖未授权模型或私有素材。
- 在无人确认时占用 GPU/显存。

## 后续扩展方向

- 模型选择：从 `object_info` 和用户配置中选择 checkpoint。
- 节点查询：封装 `list_nodes`、`get_node_info`。
- 工作流执行：增加显式 allow-list 和任务预算。
- 输出追踪：引入 `job_id`、`asset_id`、workflow provenance。
- 可视化：把 workflow 转成 Mermaid 或节点摘要。
- 错误诊断：读取 queue/history，定位失败节点。
