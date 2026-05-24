# Bridge Demo Scenarios

## 1. Codex 检查 ComfyUI 是否启动

| 项目 | 内容 |
| --- | --- |
| 用户输入 | “帮我看看本机 ComfyUI 能不能连上。” |
| Codex 应调用 | `starbridge_mcp.bridges.comfyui.status()` 和 `probe()` |
| 预期输出 | JSON schema，包含 `ok`、API URL、错误或系统状态、下一步建议 |
| 安全限制 | 只访问本地只读状态端点，不提交 workflow，不生成图片 |
| 当前是否已实现 | 已实现 |

## 2. Codex 验证 ComfyUI workflow

| 项目 | 内容 |
| --- | --- |
| 用户输入 | “检查这个 workflow JSON 是否像 ComfyUI API workflow。” |
| Codex 应调用 | `starbridge_mcp.bridges.comfyui.validate_workflow()` |
| 预期输出 | 节点数量、格式判断、缺失字段 warning |
| 安全限制 | 只做 JSON 结构检查，不调用 `/prompt` |
| 当前是否已实现 | 已实现 |

## 3. Codex 生成剪映时间线草稿计划

| 项目 | 内容 |
| --- | --- |
| 用户输入 | “用两张占位图和一段字幕做一个 9 秒短视频计划。” |
| Codex 应调用 | `starbridge_mcp.bridges.jianying.create_draft_plan()` |
| 预期输出 | `draft_plan` JSON，包含 clips、texts、audio、subtitles 轨道 |
| 安全限制 | 不写真实剪映草稿目录，不启动剪映 |
| 当前是否已实现 | 已实现 |

## 4. Codex 把分镜表转成剪映 draft_plan

| 项目 | 内容 |
| --- | --- |
| 用户输入 | “把这个三镜头分镜表变成剪映草稿计划。” |
| Codex 应调用 | `jianying.create_draft_plan()`，后续可增加 storyboard adapter |
| 预期输出 | 带时间线、字幕、素材占位符的计划文件 |
| 安全限制 | 分镜里的素材路径必须保持占位符或安全测试路径 |
| 当前是否已实现 | 部分实现；通用 `timeline_spec` 已支持，专用分镜 adapter 未实现 |

## 5. Codex 未来串联 ComfyUI 出图 + 剪映草稿生成

| 项目 | 内容 |
| --- | --- |
| 用户输入 | “用 ComfyUI 生成三张图，再做成剪映草稿计划。” |
| Codex 应调用 | 先 `comfyui.validate_workflow()` / `queue_workflow()`，再 `jianying.create_draft_plan()` |
| 预期输出 | ComfyUI job/asset 记录和剪映 `draft_plan` |
| 安全限制 | 默认不真实 queue；即使未来 queue，也必须显式允许并只引用可审查输出 |
| 当前是否已实现 | 部分实现；dry-run 和 draft_plan 已实现，真实串联未实现 |
