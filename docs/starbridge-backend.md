# StarBridge 本地后端

StarBridge 的本地 HTTP 后端复用现有 MCP 工具、工作流、Evidence（证据摘要）和安全规则。它没有增加新的软件写入权限，也不会因为提供 HTTP 接口而绕过原有的 `confirm_write`、`confirm_export` 或 `confirm_run` 确认门槛。

## 两种运行模式

### 开发模式

开发者仍可显式使用固定端口，便于调试现有网页示例：

```powershell
python -m starbridge_mcp.backend --host 127.0.0.1 --port 8765
```

或同时启动现有前后端开发服务：

```powershell
npm.cmd run app:dev
```

开发模式只允许以下浏览器来源跨端口访问，不使用通配符 CORS：

- `http://127.0.0.1:5173`
- `http://localhost:5173`

如需其他本地开发来源，必须通过重复的 `--cors-origin` 参数明确添加。

### 桌面模式

桌面模式由 Tauri 父进程启动，不面向用户手工运行。父进程负责：

- 生成每次启动都不同的临时会话令牌；
- 把令牌仅通过进程环境注入后端内存；
- 使用端口 `0` 让操作系统分配随机空闲端口；
- 传入父进程 PID，父进程消失时后端自动退出；
- 读取一行以 `STARBRIDGE_READY` 开头的机器可解析就绪信息；
- 退出前请求后端正常停止，超时后再终止子进程。

就绪信息只包含 loopback 地址、实际端口、后端 PID 和运行模式，不包含会话令牌。

## 桌面传输与 CORS 决策

P1 采用方案 A：React 组件通过 Tauri `invoke` 调用 Rust 代理，由 Rust 访问 Python 后端。会话令牌只保存在 Rust 进程内存中，不暴露给 WebView。桌面模式不接受浏览器来源，因此不会返回 `Access-Control-Allow-Origin: *`，也不依赖 CORS 来保护令牌。

现有网页开发模式继续使用受限来源的 HTTP 客户端。React 组件统一调用 `StarBridgeApiClient`，不直接保存端口或令牌。

## 身份验证

`GET /api/health` 是唯一无需会话令牌的启动探测接口，只返回最小服务状态。其他 `/api` 路由都要求当前桌面会话的 `X-StarBridge-Session` 请求头，包括：

- `/api/bootstrap`、状态、能力和资源查询；
- recipe plan、Evidence 和 guarded run；
- `/api/tools/call`；
- 审计历史读取和删除；
- `/api/lifecycle/shutdown`。

缺少令牌返回结构化 `401 authentication_required`；错误或过期令牌返回结构化 `403 authentication_failed`。比较过程使用恒定时间比较。令牌不会写入响应、运行日志、崩溃诊断、历史或配置。

## 请求边界

- 只绑定 loopback 地址，拒绝 `0.0.0.0` 和其他网络接口；
- 默认请求体上限为 1 MiB；
- 拒绝非法、负数或超过上限的 `Content-Length`；
- 带正文的 API 请求只接受 `application/json`；
- API 响应包含 `Cache-Control: no-store`；
- 进程边界错误只返回普通说明和恢复步骤，不返回堆栈、会话令牌或未脱敏路径。

## 应用数据目录

正式 Windows 桌面模式默认使用：

```text
%LOCALAPPDATA%\StarBridge\
├─ data\
├─ history\
├─ logs\
├─ cache\
└─ diagnostics\
```

开发与测试可通过 `STARBRIDGE_APP_DATA_DIR` 或 `--app-data-dir` 覆盖根目录。旧的历史文件位置仍可用 `--history-path` 显式指定，但仓库内的 `examples/output` 不再是正式默认位置。后端不会借此扫描应用数据目录以外的用户文件，现有 safe roots 和路径脱敏规则保持不变。

## API 兼容性

原有 API 路径保持不变：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 最小启动探测；桌面模式唯一免鉴权接口。 |
| `GET` | `/api/bootstrap` | 前端启动数据，包括能力、工作流、历史和 safe roots。 |
| `GET` | `/api/status` | 安全的软件桥状态摘要。 |
| `GET` | `/api/capabilities` | 能力矩阵。 |
| `GET` | `/api/tools`、`/api/resources` | MCP 工具和资源描述。 |
| `GET`、`POST` | `/api/recipes/{recipe_id}/plan` | 只生成计划，不执行真实写入。 |
| `GET`、`POST` | `/api/recipes/{recipe_id}/evidence` | 生成证据摘要。 |
| `POST` | `/api/recipes/{recipe_id}/run` | 记录已确认的安全 dry-run 请求；当前产品 UI 不直接启动创意软件。 |
| `GET`、`DELETE` | `/api/audit/history` | 读取或清除本地审计历史。 |
| `POST` | `/api/tools/call` | MCP 工具调用兼容层。 |
| `POST` | `/api/lifecycle/shutdown` | 由桌面父进程请求优雅停止。 |

## 开发验证

开发模式下可直接验证公开健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

桌面模式的其他接口应通过 Tauri 代理验证，不应把会话令牌粘贴进命令历史。
