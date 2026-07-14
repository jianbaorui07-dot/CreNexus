# StarBridge Photoshop Node Proxy

Starts a local HTTP JSON-RPC bridge between the StarBridge MCP server and the Photoshop UXP plugin.

## Start

```powershell
cd node_proxy\photoshop-bridge
npm install
npm start
```

## Endpoints

- `GET /health`
- `GET /bridge/status`
- `POST /rpc`

详细方法白名单、256 KiB 请求上限、输出路径和 BatchPlay 副本规则见 `docs/photoshop-node-proxy-security.md`。

## Notes

- The UXP plugin connects to `ws://127.0.0.1:8971/uxp`.
- If no UXP client is connected, `/rpc` returns `uxp_client_not_connected`.
- 写请求必须显式确认；Node Proxy 会在进入 UXP 前拒绝仓库 `sandbox/`、`output/` 和 `examples/output/photoshop/` 之外的预览路径。
- Typed BatchPlay 只在自动复制的临时文档上执行，不覆盖原活动文档。
