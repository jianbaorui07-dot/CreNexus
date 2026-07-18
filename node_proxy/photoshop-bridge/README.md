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
- 写请求必须显式确认；传统预览只允许仓库 `sandbox/`、`output/` 和 `examples/output/photoshop/`，`ps.production.execute_confirmed` 只允许 StarBridge 应用数据目录中的 hash 绑定项目源和任务产物。
- 生产协议使用固定输出文件名和代理推导的 `.part` 临时文件；成功后才原子提升，失败只清理本任务应用拥有的临时文件。
- Typed BatchPlay 只在自动复制的临时文档上执行，不覆盖原活动文档。
