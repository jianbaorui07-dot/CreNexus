# StarBridge Desktop（P1 安全运行基座）

这个目录是正式桌面应用工程，不再放在 `examples/`。它保留 React、Vite 和 TypeScript 前端，并使用 Tauri 2 管理一个由 PyInstaller 打包的 Python sidecar（随桌面程序运行的本地后台程序）。

P1 只实现启动、连接、恢复和诊断基座，不代表安装器、完整工作流界面或真实创意软件控制已经验收。

P2 已开始建立公开的离线授权基础：桌面端可以导出脱敏设备申请，并在 Rust 层导入和验证 Ed25519 签名授权。当前 Community 构建没有生产验签公钥，也不包含 Pro 功能代码。商业边界、建议价格和签发流程以 [`docs/OFFLINE_COMMERCIALIZATION.md`](../../docs/OFFLINE_COMMERCIALIZATION.md) 为准。

## 目录职责

```text
apps/starbridge-desktop/
├─ src/                    # 最小 React 状态界面与统一 API 客户端
├─ src-tauri/              # Tauri 2、最小 capabilities 和 sidecar 生命周期
├─ scripts/                # PyInstaller 构建、依赖检查与 sidecar 验收
└─ README.md
```

现有 `examples/starbridge_frontend` 仍作为网页/开发示例保留。VectorFlow Studio 也继续通过 `python -m starbridge_mcp.vectorization.app` 独立运行；P1 没有删除、嵌入或重写矢量化引擎。

## 安全架构

P1 采用方案 A：React WebView 只调用 Tauri command，由 Rust 代理访问 Python 后端。正式桌面模式不向 WebView 暴露随机端口或会话令牌，Python 端也不配置浏览器 CORS 来源；浏览器开发模式才使用独立的 `HttpTransport` 和明确开发来源。

```text
React 组件
    │ 统一 StarBridgeApiClient
    ▼
DesktopTransport ── Tauri invoke ── Rust 受限代理
                                      │ 内存会话令牌
                                      ▼
                         127.0.0.1:随机端口 Python sidecar
```

- WebView 不持有后端端口或会话令牌。
- Rust 代理不接受任意 URL、任意请求头或任意 shell 命令。
- P1 的通用代理只允许读取 health、bootstrap、status、capabilities 等安全启动数据。
- guarded run、`tools/call` 和删除历史没有通过通用桌面代理开放；后续确认界面必须使用更窄的专用命令。
- sidecar 最多自动恢复一次，之后要求用户查看诊断或手动重启。
- 主程序退出时先请求后端优雅停止，超时后才终止子进程。

## 前端开发与测试

```powershell
npm.cmd install --prefix apps\starbridge-desktop
npm.cmd test --prefix apps\starbridge-desktop
npm.cmd run build --prefix apps\starbridge-desktop
```

浏览器开发模式使用 `HttpTransport` 和显式开发端口；正式 Tauri 构建使用 `DesktopTransport`。组件只依赖统一客户端。

## 构建 one-folder sidecar

脚本只安装仓库局部 `.venv-build`，不会安装系统组件或请求管理员权限：

```powershell
powershell -ExecutionPolicy Bypass -File apps\starbridge-desktop\scripts\Build-Sidecar.ps1
```

它使用固定的 PyInstaller 版本，将核心 HTTP/MCP 后端打成 one-folder，并明确排除 PySide6、OpenCV、NumPy、Pillow 和 `starbridge_mcp.vectorization`。`.spec` 明确列出核心 hidden imports，数据文件列表保持为空。构建脚本优先使用 `CARGO_BUILD_TARGET` 或 Rust host triple；原生工具链缺失时按当前 Windows 架构推导，也可用 `-TargetTriple` 显式指定。构建产物会暂存到符合 Tauri target triple 命名的 `src-tauri/binaries/`，且不会被 Git 跟踪。

真实验证 sidecar 的随机端口、鉴权、bootstrap、优雅退出和端口释放：

```powershell
powershell -ExecutionPolicy Bypass -File apps\starbridge-desktop\scripts\Test-Sidecar.ps1
```

## Tauri 本地开发门槛

先运行只读检查：

```powershell
powershell -ExecutionPolicy Bypass -File apps\starbridge-desktop\scripts\Check-Prerequisites.ps1
```

依赖齐全后：

```powershell
npm.cmd run tauri:dev --prefix apps\starbridge-desktop
```

P1 的无安装器本地构建命令为：

```powershell
npm.cmd run tauri:build --prefix apps\starbridge-desktop
```

P2 增加了仅用于本地验收的当前用户 NSIS 构建入口：

```powershell
npm.cmd run tauri:bundle:nsis --prefix apps\starbridge-desktop
```

该入口不需要 StarBridge 服务器。当前开发机已完成一次构建、当前用户安装、真实窗口启动、正常关闭和卸载测试；由于仍没有 Authenticode 证书和干净机器验收，产物不能作为公开收费安装包。

## one-folder 发布边界

Tauri 会将 target-triple sidecar 作为 external binary，并把 PyInstaller `_internal` 目录作为资源复制。当前脚本已验证直接暂存布局；真正的 Tauri 编译与安装布局仍必须在 Rust stable-msvc、Microsoft C++ Build Tools 和 WebView2 均可用的 Windows 环境中复核，不能仅凭工程文件宣称可发布。
