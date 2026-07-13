# Codex 跨软件控制规划器

`starbridge.control_plan` 是 Codex 面向多类创意软件的统一只读路由入口。它根据任务目标选择 Photoshop、Illustrator、ComfyUI、CAD / AutoCAD、Blender 或剪映 / CapCut，并返回分阶段工具顺序。

这个工具只做规划：不启动桌面软件、不读取素材或工程、不写文件。真实修改仍必须调用对应 guarded tool，并满足它自己的 `dry_run`、确认参数和 sandbox 输出限制。

## 输入 schema

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `goal` | 是 | 1–500 字符的任务目标；不得包含真实路径、token 或私有素材内容 |
| `preferred_bridge` | 否 | 默认 `auto`；也可显式指定 `photoshop`、`illustrator`、`comfyui`、`autocad_dxf`、`blender`、`jianying_capcut` |
| `include_guarded_candidates` | 否 | 默认 `false`；设为 `true` 只会列出确认操作候选，不会执行 |

## MCP 调用示例

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "starbridge.control_plan",
    "arguments": {
      "goal": "为公开商品图规划 Photoshop 抠图和预览导出",
      "preferred_bridge": "auto",
      "include_guarded_candidates": false
    }
  }
}
```

返回计划固定包含以下安全阶段：

1. `discover`：先检查 `starbridge.safe_roots` 和软件桥状态；ComfyUI 额外加入默认 plan-only 的 `comfyui.queue_snapshot`；
2. `plan`：调用软件专属的只读 planner / validator；
3. `visual_review`：仅 ComfyUI 路线使用，把内联 workflow 转为脱敏 Mermaid；
4. `observe`：用 `starbridge.operation_context` 形成白名单 before/after 状态差异；
5. `review`：预览并校验 EvidenceManifest；
6. `confirmed_action_candidate`：仅在显式请求时列出，仍需用户确认后另行调用。

每个 `starbridge.recipe_plan` 还会返回相同的 `operation_context` 契约。Codex 应在首个主要动作前、主要动作后和失败后调用该工具，只传入白名单指标并串联 `context_id`；这不会自动读取桌面软件。

ComfyUI 路线还返回 `queue_snapshot` 契约和 `queue_backpressure_reviewed` 质量门。规划器只列出 `probe=false`；调用方要读取真实队列必须显式改为 `probe=true`，并且只有 live snapshot 返回 `decision=idle` 与 `safe_to_enqueue=true` 才表示当前没有 backlog。这不代替 `agent_run` 的真实提交确认。

目标无法可靠归类时，工具返回 `needs_clarification=true` 和可选软件桥，不会猜测执行。

## 软件路由

| 软件桥 | 典型目标 | 计划工具 |
| --- | --- | --- |
| Photoshop | 修图、抠图、图层、蒙版、Camera Raw | `photoshop.recipe_plan` |
| Illustrator | 矢量、画板、SVG、Image Trace | `illustrator.preflight` |
| ComfyUI | 文生图、图生图、workflow | `comfyui.queue_snapshot` → `comfyui.workflow_build_plan` |
| CAD / AutoCAD | 工程图、DXF、结构化 CAD plan | `autocad_dxf.create_dxf_plan` |
| Blender | 三维、建模、场景、渲染规划 | `blender.scene_plan` |
| 剪映 / CapCut | 视频、字幕、时间线、草稿摘要 | `jianying_capcut.draft_structure` |

## 安全边界

- 输出始终为 `dry_run=true`。
- 不接受任意脚本、任意文件路径或目录扫描参数。
- 不读取 PSD、AI、DWG、`.blend`、CapCut 草稿、模型或生成结果。
- 不绕过登录、授权、验证码、OAuth 或桌面确认。
- 即使返回 guarded candidate，也不代表真实软件已经运行或验证。
