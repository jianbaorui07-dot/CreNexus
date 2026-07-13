# ComfyUI 只读 Queue Snapshot

`comfyui.queue_snapshot` 把 ComfyUI `/queue` 转成适合 Codex 判断 backpressure 的脱敏摘要。它不返回 workflow、prompt、模型名、节点输入、history 或输出文件，也不会提交、移动、取消任务。

Schema：`starbridge.queue-snapshot.v1`。

## 为什么需要这一层

单份 `JobStatus` 只能回答一个 job 的状态，不能回答当前是否已经有任务运行、是否存在 backlog、下一次提交是否会堆到慢任务后面。Queue Snapshot 用一次只读调用提供：

- running / pending / depth 的权威计数；
- 只由原始 prompt id 单向哈希得到的逻辑 job id；
- pending 的 1-based 顺序；
- `idle`、`busy`、`backlog`、`planned`、`unavailable` 决策；
- `safe_to_enqueue` backpressure gate；
- 可选、只含数值的单调 progress 摘要。

ComfyUI queue item 的 priority number 不是剩余任务数，前插任务时还可能是负数。因此总深度只按 `/queue` 返回的 running 和 pending 数组长度计算。

## 调用模式

默认调用不会访问网络：

```json
{
  "name": "comfyui.queue_snapshot",
  "arguments": {}
}
```

它返回 `mode=planned`、`safe_to_enqueue=false`，提醒调用方先显式选择 live probe。真实读取必须传入：

```json
{
  "name": "comfyui.queue_snapshot",
  "arguments": {
    "probe": true,
    "timeout": 5,
    "max_items": 25
  }
}
```

只允许 `http://127.0.0.1`、`http://localhost` 或 IPv6 loopback，拒绝账号信息、query、fragment、额外路径和 redirect。默认端点是 `http://127.0.0.1:8188/queue`。

## 结构化 progress

`/queue` 不提供节点或 sampler 的实时步进。调用方若已经从受控 WebSocket adapter 得到纯数值事件，可以传入：

```json
{
  "progress": {
    "current": 5,
    "total": 14,
    "previous": 4
  }
}
```

工具只接受非负整数，要求 `current <= total` 且 `current >= previous`，再输出百分比。它不会接受 node name、prompt id、文件名或任意 message，因此不能泄漏工作流内容。没有 progress 输入时会明确返回 `available=false`，不会用 queue depth 冒充执行进度。

## 输出边界

安全输出示例：

```json
{
  "schema_version": "starbridge.queue-snapshot.v1",
  "mode": "live",
  "decision": "backlog",
  "queue": {
    "running_count": 1,
    "pending_count": 2,
    "depth": 3,
    "backlog": true,
    "safe_to_enqueue": false,
    "running_jobs": [{"logical_job_id": "job_0123456789ab", "status": "running", "position": 0}],
    "pending_jobs": [{"logical_job_id": "job_abcdef012345", "status": "pending", "position": 1}]
  }
}
```

`max_items` 只限制返回的 job 摘要数量，不改变完整计数；截断时 `truncated=true`。任何网络或 payload 错误只返回固定错误码，不回显 URL、prompt id 或服务器响应。

## 与控制规划器的关系

ComfyUI 路线在生成或列出 guarded action 前先调用本工具。只有 live snapshot 明确返回 `decision=idle` 和 `safe_to_enqueue=true`，才表示当前队列没有 backpressure；这仍不等于已经获得生成确认。真实 `/prompt` 提交继续要求 `comfyui.agent_run` 的显式确认门。

当前版本不读取 `/history`、不打开 WebSocket、不发送 MCP `notifications/progress`，也不提供 cancel / clear / move。后续能力必须分别补文档、schema、测试和确认策略。
