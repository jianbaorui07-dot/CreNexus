# P1 Windows 桌面构建前置条件

状态：**PASS**（2026-07-16 21:55，Asia/Shanghai，本机真实构建与运行验收）

本文件记录构建环境边界，不代表普通用户将来需要安装这些工具。正式安装包的目标仍是：最终用户无需预装 Python、Node.js、npm 或 Rust，也无需打开 PowerShell。

## 本机审计结果

| 组件 | 当前状态 | P1 用途 |
| --- | --- | --- |
| Node.js / npm | 已安装：Node.js `v24.16.0`，npm `11.13.0` | React/Vite 构建与前端测试 |
| Python 3.12 | 已安装：`3.12.10` | 后端测试和 PyInstaller 构建 |
| 项目 `.venv` | 可用 | 运行现有完整测试 |
| `.venv-build` / PyInstaller | 已由仓库局部脚本建立；PyInstaller 6.16.0 | one-folder sidecar 构建 |
| WebView2 Runtime | 已安装：`150.0.4078.65` | Tauri Windows WebView |
| `rustc` / `cargo` | 已安装：rustc `1.97.1`，cargo `1.97.1` | 编译 Tauri Rust 外壳 |
| Rust stable-msvc | 已安装并启用：`stable-x86_64-pc-windows-msvc` | 生成 Windows MSVC 目标程序 |
| Microsoft C++ Build Tools | 已安装：Build Tools 2022 `17.14.36`，MSVC `19.44.35228`，link `14.44.35228.0` | Rust/Tauri Windows 链接 |
| Windows SDK | 已安装：`10.0.26100.0` | Windows 头文件、库和资源编译 |

复核命令 `Check-Prerequisites.ps1 -Json` 的退出码为 `0`，`native_tauri_ready` 为 `true`。`tauri info` 同时识别到 WebView2、MSVC、Rust stable-msvc、Node.js 和 npm。

本轮已经真实运行 `cargo metadata`、`cargo check`、Rust 单元测试、Tauri development build、Tauri release `--no-bundle` build、开发窗口和 release 窗口。WebView 通过 Tauri invoke 调用 Rust 受控代理，再以仅驻留 Rust/Python 内存的会话凭据请求 Python sidecar `/api/bootstrap`，返回 HTTP 200。正常关闭后 sidecar、随机 loopback 端口和临时本机调试端口均退出，未发现孤儿进程。

## 本轮安装记录与影响

用户明确允许安装缺失依赖后，本轮只安装了 P1-B 原生构建所需的工具链。没有安装 StarBridge 服务、没有开放防火墙或公网端口，也没有创建 Windows 服务、计划任务或开机自启。

| 依赖 | 必要内容 | 典型规模 | 管理员权限与影响 |
| --- | --- | --- | --- |
| Rustup + Rust stable MSVC | `rustup`、`rustc`、`cargo`，host 为 `x86_64-pc-windows-msvc` | 实际安装到当前用户工具链目录；Cargo 首次构建另外产生受 Git 忽略的缓存 | 当前用户安装；新终端会读取更新后的 PATH |
| Visual Studio Build Tools 2022 | “使用 C++ 的桌面开发”、MSVC x64/x86、Windows 11 SDK 10.0.26100 | 安装器下载并安装所选工作负载及推荐组件 | 系统级安装已完成；`vswhere` 报告 complete/launchable，无需重启 |
| WebView2 Runtime | 已满足，无需本轮安装 | 0 | 不应重复安装 |

系统上原有 Visual Studio Community 2026 保留不变；它可以作为 IDE，但本次 Tauri 构建实际使用已验证的 Build Tools 2022。两者可共存。

## 已完成的安装与验证

这些依赖只供开发与本机验收。普通用户最终使用正式安装包时不应需要它们：

1. Rustup `1.29.0` 已安装，active toolchain 为 `stable-x86_64-pc-windows-msvc`。
2. Build Tools 2022、MSVC x64/x86 和 Windows SDK `10.0.26100.0` 已安装。
3. WebView2 Runtime `150.0.4078.65` 已确认可用。
4. `cl.exe` 和 `link.exe` 已在 Visual Studio developer environment 中真实运行；Cargo 后续完成了实际 Windows 链接。

Tauri 官方 Windows 前置条件说明见 [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/)。

## 复核命令

```powershell
powershell -ExecutionPolicy Bypass -File apps\starbridge-desktop\scripts\Check-Prerequisites.ps1
rustc --print host-tuple
cargo --version
```

期望 target triple 为 `x86_64-pc-windows-msvc`（x64 Windows）。不同架构必须重新生成带对应 triple 的 sidecar 文件名，不能把 x64 文件伪装成其他目标。

## 本轮已执行的 P1-B 验收

- `cargo check --all-targets`：通过；
- Rust unit tests：3/3 通过；
- `tauri dev`：真实打开窗口并启动 sidecar；
- WebView → Tauri invoke → Rust proxy → authenticated bootstrap：HTTP 200；
- release `tauri build --no-bundle`：通过；
- release 可执行程序首次启动、关闭、重新启动：通过；
- 中文与空格目录中的 release 副本：真实启动并正常关闭；
- sidecar 生命周期脚本：随机 loopback、认证、优雅退出、父进程消失退出、端口释放、无孤儿和凭据不泄露全部通过；
- 前端 Vitest：10/10 通过；TypeScript/Vite production build：通过；
- Python full unittest：515/515 通过，4 项按既有条件跳过；
- Python ruff、format check 和 `security_check.py`：通过。

未运行：NSIS/MSI 安装器、代码签名、自动更新、Windows Defender/第三方杀毒误报测试、非管理员 Windows 账户专项测试。这些项目不属于本轮非安装器 P1-B MVP 的 PASS 条件，也不得据此宣称已有可下载或已发布的 Windows 安装包。
