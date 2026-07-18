# Illustrator realtime Node Proxy

本机只监听 `127.0.0.1:8972`。它在内存中维护最新脱敏状态和最新 Illustrator 窗口帧，并只转发白名单 JSON-RPC 命令。

```powershell
npm install --prefix node_proxy/illustrator-bridge
npm.cmd run illustrator:realtime:proxy
```

Illustrator 会话适配器连接 `ws://127.0.0.1:8972/illustrator`。WGC companion 将 JPEG/PNG POST 到 `/capture/frame`，并必须带 `X-StarBridge-Capture-Target: illustrator-window`。

匠心矢量设计命名使用四个专用白名单方法：`apply_artisan_map`、`readback_artisan_map`、`commit_artisan_map` 和 `rollback_artisan_map`。应用与回滚要求 `confirm_write=true`；应用还必须匹配代理最新的 `state_revision`。代理不接受 JSX、任意脚本、文件路径或非白名单方法。
