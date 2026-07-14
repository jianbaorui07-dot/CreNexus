# Photoshop Node Proxy 安全协议

## 目标

Photoshop UXP 插件为了让本机 MCP 非交互地导出 sandbox 预览，当前仍声明 `localFileSystem: fullAccess`。该权限只表示宿主允许访问文件系统，不代表 StarBridge 接受任意路径。Node Proxy 和 UXP 必须继续执行更窄的运行时边界。

## 请求边界

Node Proxy 只接受以下本机 JSON-RPC 方法：

| 方法 | 默认行为 | 写入条件 |
| --- | --- | --- |
| `starbridge.ping` | 只读 | 无 |
| `ps.document.info` | 当前会话脱敏摘要 | 无 |
| `ps.layers.list` | 当前会话逻辑 ID、类型和状态 | 无 |
| `ps.batchplay.validate.local` | 只验证 typed descriptor | 无 |
| `ps.preview.export` | 默认 dry-run | `confirm_write=true`，且输出位于仓库 sandbox |
| `ps.camera_raw.tune` | 默认 dry-run | apply 需要 `confirm_apply=true`；导出另需 `confirm_export=true` |
| `ps.batchplay.execute_confirmed` | 不执行任意 action | `confirm_write=true`，验证通过，并在自动复制的临时文档上执行 |

请求体最大 256 KiB。未列出的方法、重复的在途 request ID、路径逃逸和缺少确认的写请求都必须在进入 UXP 前拒绝。

协议 schema：`examples/photoshop_bridge/protocols/node_proxy_rpc.v1.schema.json`。

## 输出 sandbox

Node Proxy 从自身源码位置推导仓库根目录，不信任调用方传入的根路径。真实预览只允许写入：

- `sandbox/`
- `output/`
- `examples/output/photoshop/`

输出文件必须是 `.png`，不得使用 `..`、相对路径、UNC 路径或仓库外绝对路径。UXP 收到请求后还会重复检查允许根和扩展名，避免绕过 Node Proxy 直接调用插件 handler。

Adobe 官方 UXP 文件权限文档建议优先使用插件专属目录或文件选择器。StarBridge 保留 `fullAccess` 只为已确认的本机自动化预览；不得把它扩展为任意文件读取、删除或覆盖能力。

## BatchPlay sandbox

- descriptor 先经过 Python 与 UXP 双重 allowlist。
- 拒绝文件路径、脚本、按名称或数字 ID 指向其他文档/图层的 target。
- 写入前在 `executeAsModal` 内复制当前文档，后续 descriptor 只作用于新的活动副本。
- 复制文档先注册为 auto-close；请求失败或用户取消时由 Photoshop 无保存关闭。
- 成功时返回原文档和 sandbox 文档的会话 ID，不保存或覆盖原文档。

## 验证

```powershell
python -m unittest tests.test_photoshop_node_proxy tests.test_photoshop_adapter_v1
node --check node_proxy/photoshop-bridge/server.js
python scripts/security_check.py
python scripts/starbridge_preflight.py --markdown
```
