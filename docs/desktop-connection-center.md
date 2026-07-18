# 桌面连接中心协议

StarBridge Desktop 每次启动本地 sidecar 时都会创建一个新的短期会话。制图功能只在当前会话已经由 Codex 通过 StarBridge MCP 明确配对后开放；旧会话、旧配对码和仅检测到安装的软件都不能绕过该门槛。

## 连接流程

1. 桌面 sidecar 在应用数据目录的 `cache` 子目录创建一次性挑战文件。文件只包含随机会话 ID、短配对码和创建时间，不包含 Codex token、Cookie、账号或素材路径。
2. 用户在连接中心确认“安装/更新 Codex 连接器”。StarBridge 只更新 Codex 个人配置中的 `STARBRIDGE DESKTOP CONNECTOR` 托管区块，保留其他配置。
3. StarBridge 通过官方 `codex://new?prompt=...` 深链接打开一个新任务并预填配对指令。深链接不会替用户发送消息。
4. Codex 调用 `starbridge.desktop_pair`，同时提交当前配对码、`dry_run=false`、`confirm_pairing=true` 和 `confirm_write=true`。MCP 进程读取同一应用数据目录中的挑战并写入当前会话回执。
5. 桌面端轮询 `GET /api/connections`。只有回执与当前会话匹配时，`drawing_enabled` 才为 `true`。

本流程不会读取 `auth.json`，不会复制 Codex 登录凭据，也不会把本地服务暴露到局域网或公网。

## MCP tool：`starbridge.desktop_pair`

该工具只写入一个可撤销的本地配对回执，不启动创意软件，不读取用户文件。

输入：

- `pairing_code`：连接中心当前显示的 8 位大写字母/数字。
- `dry_run`：默认 `true`，只验证计划；实际关联必须明确设为 `false`。
- `confirm_pairing`：必须显式为 `true`。
- `confirm_write`：必须显式为 `true`，确认写入可撤销的本地配对回执。

安全默认：

- 缺少确认时拒绝写入。
- 配对码错误、过期或桌面端未运行时返回结构化错误。
- sidecar 重启会轮换会话 ID，使旧回执自动失效。
- 输出只说明是否配对成功，不返回应用数据目录或会话 ID。

## HTTP 接口

- `GET /api/connections`：返回 `starbridge.desktop-connections.v2` 状态，包括 Codex 配对、本机创意软件安装/运行/配对线索以及 `drawing_enabled`。
- `POST /api/connections/codex/install`：需要 `confirm_install=true`，只安装或更新托管的 Codex MCP 配置区块。
- `POST /api/connections/codex/reset`：需要 `confirm_reset=true`，轮换当前配对挑战；用于重新关联，不会结束 Codex 或创意软件进程。
- `POST /api/connections/applications/pair`：需要固定 `application_id` 和 `confirm_pairing=true`；只为当前 sidecar 会话记录一次可撤销配对，不打开文档、不写入外部软件。
- `POST /api/connections/applications/reconnect`：需要 `confirm_reconnect=true`；重新执行对应适配器的只读握手，不重启外部软件。
- `POST /api/connections/applications/disconnect`：需要 `confirm_disconnect=true`；删除本次 sidecar 会话的本地配对回执，不结束外部软件进程。

桌面 WebView 只能通过带当前 sidecar 会话凭据的 Rust 代理访问这些接口。开发 HTTP 模式不允许修改 Codex 个人配置。

## 本机创意软件状态与配对

连接中心只使用固定进程名、Windows App Paths、明确的环境变量以及 ComfyUI 回环接口做有限探测，不递归扫描磁盘：

- `not_installed`：没有找到安装或运行线索。
- `installed`：找到安全安装线索，但软件未运行。
- `running`：找到对应进程；表示可按任务尝试桥接，不等于已经修改文档。
- `bridge_ready`：本地回环接口或可验证桥接会话可用。
- `unavailable`：本轮探测失败；用户可安全地重新检测。

每个软件还会返回独立的 `pairing_state`：

- `not_available`：没有安装线索，不能配对。
- `open_required`：已安装但没有运行；需要用户手动打开软件。
- `ready_to_pair`：已运行，等待用户明确配对。
- `paired`：已配对，并通过只读 COM 或回环 HTTP 握手。
- `paired_limited`：已与当前运行会话配对，但尚无仓库内验证过的控制适配器；只支持存在性检测和任务路由。
- `reconnect_required`：本次 sidecar 曾配对，但软件已经停止或桥接握手失效。
- `unavailable`：本轮探测失败。

适配器边界：

- Photoshop、Illustrator、AutoCAD：只连接已经运行的 COM 对象；配对阶段不创建文档、不读取文档内容、不执行脚本。
- ComfyUI：只访问配置的本机回环地址，配对阶段读取 `/system_stats`，不提交 workflow。
- Blender：当前只做进程会话配对和任务路由；安装并验证 Blender 插件前不会显示为“桥接可用”。
- 剪映 / CapCut：当前只做进程会话配对和任务路由；没有稳定公开桌面控制 API，不读取草稿、账号或素材。

创意软件配对必须在当前 Codex 会话已经关联后进行。sidecar 重启或 Codex 重新关联会使所有创意软件配对自动失效，避免旧会话继续获得连接状态。

“重新检测”不会结束软件进程。“重新连接”只刷新 StarBridge 的适配器握手。“重启本地桥接”只重启 StarBridge 自己管理的 sidecar，绝不强制关闭 Photoshop、Illustrator、AutoCAD、Blender、ComfyUI 或剪映/CapCut。
