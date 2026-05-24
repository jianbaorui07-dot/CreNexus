# ComfyUI Bridge MVP 示例

这个目录演示 StarBridge 如何安全检查 ComfyUI。本示例不会安装模型、不会下载 custom node、不会提交真实生成任务。

## 启动前

先手动启动 ComfyUI。默认 API 地址：

```powershell
http://127.0.0.1:8188
```

如果你的 ComfyUI 不在默认地址，设置：

```powershell
$env:STARBRIDGE_COMFYUI_URL="http://127.0.0.1:8188"
```

## 只读状态检查

```powershell
python examples\comfyui\check_comfyui_status.py
```

服务未启动时也会输出结构化 JSON，`ok=false`，并给出 `warnings` 和 `next_steps`。

## workflow dry-run 校验

```powershell
python examples\comfyui\validate_workflow.py
```

`sample_workflow_minimal.json` 只用于结构验证，里面的 checkpoint 是占位名称，不包含真实模型路径。

## 真实 queue 保护

`queue_workflow` 默认 `dry_run=True`。只有同时满足以下条件才会尝试提交到 ComfyUI：

- 调用方显式传入 `dry_run=False`
- 设置 `$env:STARBRIDGE_COMFYUI_ALLOW_QUEUE="true"`

默认行为不会误跑大型生成任务。
