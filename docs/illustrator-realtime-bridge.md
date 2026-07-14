# Illustrator 实时桥接

## 结论

Illustrator 当前没有本仓库可验证的 Adobe 官方公开 UXP 宿主标识，因此仓库不提交无法安装验证的 `host: ILST` 清单。实时桥采用三条本机通道：

1. 屏幕通道：Windows Graphics Capture companion 只向代理推送 Illustrator 窗口帧。
2. 状态通道：Illustrator 会话适配器发送脱敏的文档计数、选择、图层、画板、缩放和工具摘要。
3. 操作通道：Node Proxy 只转发 schema 白名单中的命令；写操作要求 `confirm_write=true`。

```text
Codex -> HTTP JSON-RPC -> Node Proxy -> WebSocket -> Illustrator session adapter
                                      <- state/event <-
      <- latest frame metadata ------- WGC companion
```

默认端口为 `8972`，只监听 `127.0.0.1`。代理不保存图片，只在内存中保留最新一帧，最大 4 MiB。

## 状态协议 v2

`realtime_state.v2` 把实时状态收紧为可审计的最小摘要：

- 不发送文档名、图层名、画板名、对象名、文件路径、链接素材或字体信息。
- 对象、图层和画板仅使用当前会话内的逻辑 ID；重连或刷新状态后不得长期复用。
- 每条状态带 `protocol_version=2`、单调递增的 `sequence` 和 `captured_at`。
- Node Proxy 接收后重新生成可信的 `revision` 和 `received_at`，并在 `/state` 返回 `age_ms` 与 `stale`。
- Node Proxy 只输出 schema 白名单字段；上游误带的名称和路径字段会被丢弃，缺少必要字段或 sequence 倒退的状态会被拒绝。
- `/state?max_age_ms=2000` 可设置本次读取允许的最大状态年龄，范围为 100–60000 ms；默认 2000 ms。
- 不符合必要 v2 结构的状态会被拒绝，不会覆盖上一条有效状态；拒绝计数可从 `/health` 查看。

状态 schema：`examples/illustrator_bridge/protocols/realtime_state.v2.schema.json`。

## 运行

```powershell
npm.cmd run illustrator:realtime:proxy
npm.cmd run illustrator:realtime:capture
```

检查状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8972/health
Invoke-RestMethod 'http://127.0.0.1:8972/state?max_age_ms=2000'
Invoke-RestMethod http://127.0.0.1:8972/frame/meta
```

浏览器连续预览：`http://127.0.0.1:8972/preview`。

只读命令 `illustrator.document_info`、`illustrator.get_state`、`illustrator.zoom_to_selection` 不要求写入确认。`illustrator.select_object`、`illustrator.set_fill`、`illustrator.move_object`、`illustrator.create_path` 必须显式提供 `confirm_write=true`；对象只能通过会话内 object ID 引用，不接受文件路径或任意脚本。

## 安全边界

- 不打开任意工程文件，不读取链接素材路径，不执行任意 JSX。
- 状态事件不得包含文档名、完整路径、用户名、账号、字体信息或链接素材信息。
- 截图只允许声明为 Illustrator 窗口帧；代理拒绝桌面帧。
- WGC companion 必须按窗口句柄绑定 Adobe Illustrator，不得使用全局或桌面捕获项。
- WGC companion 默认 3 FPS、最长边 1440 px、JPEG 质量 72；帧只在内存和本机 HTTP 中流转，不写入文件。
- CI 只测试协议、状态脱敏、新鲜度和安全拒绝；真实 WGC、COM、GUI 和 Adobe 授权只在 Windows 本机验证。

## 验证

```powershell
python -m unittest tests.test_illustrator_realtime_proxy tests.test_illustrator_uxp_bridge
python scripts/security_check.py
python scripts/starbridge_preflight.py --markdown
```
