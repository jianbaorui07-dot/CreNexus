# 新 Mac 环境基线测试报告

- 阶段：0（仅环境与基线，不改业务代码）
- 日期：2026-07-22（Asia/Shanghai）
- 分支：`codex/macos-handoff`
- 基线提交：`2eecfe3e52be78ef79327b4f0ce34bc81dcc2503`
- 周额度闸门：7 天窗口 `usedPercent=2`，低于 8% 停止线，允许执行本阶段

## 范围与保护边界

本阶段只读取仓库规则、交接说明、权威配置与现有 workflow；安装本机缺失工具和被忽略的项目依赖；运行基线；新增本报告。未导入、修改、暂存或删除以下既有未跟踪工作：

- `CreNexus_Mac交接与CI执行说明书.docx`
- `SKILL.md`
- `starbridge-macos-adapter/`（4 个文件）

运行产生的 `.venv/`、`apps/starbridge-desktop/node_modules/`、`apps/starbridge-desktop/dist/` 和 `apps/starbridge-desktop/src-tauri/target/` 均已被 Git 忽略，不进入提交。未执行 `reset`、`clean`、`stash`，未改变 Homebrew、Gatekeeper、SIP、TCC 或 Rosetta。

CodeGraph 当前未注册且本轮无可用 CodeGraph 工具；本阶段没有借用其他仓库索引，也没有修改业务代码。此能力缺口需在进入业务改动前另行处理。

## 仓库声明与本机版本

仓库没有 `.python-version`、`.nvmrc`、`.node-version` 或 `rust-toolchain.toml`。权威声明为：

- Python：`pyproject.toml` classifiers 声明 3.10–3.13，但未设置 `requires-python`；交接说明推荐 3.12，现有 CI 覆盖 3.11–3.13。
- Node：无仓库级固定版本；现有 CI 使用 Node 22，交接说明优先 Node 22。
- Rust：无固定 toolchain；交接说明使用 stable。

| 项目 | 版本/状态 | 备注 |
| --- | --- | --- |
| 架构 | `arm64` | Rust host 为 `aarch64-apple-darwin` |
| macOS | 27.0（Build 26A5378n） | 当前主机 |
| Xcode | 26.5（Build 17F42） | 已存在，未安装或重装 |
| Git | 2.50.1 | Apple Git-155 |
| 系统 Python | 3.14.6 | 超出仓库已声明测试范围，未用于项目基线 |
| 项目 Python | 3.12.13 | 由 `uv` 安装；`.venv` 按手册使用 pip editable 安装 `.[dev,vectorization]` |
| 系统 Node | 24.15.0 | 仓库未固定；未改系统安装 |
| 基线 Node | 22.23.1 | 以临时隔离 runtime 复现 CI 主版本 |
| npm | 11.12.1 | 前端依赖按 lockfile 安装，审计为 0 vulnerabilities |
| Rust/Cargo | 1.97.1 stable | minimal profile，host `aarch64-apple-darwin` |
| Homebrew | 未安装 | 按禁止事项未自动安装 |

## 基线命令与结果

为避免既有未跟踪 `SKILL.md` 被仓库扫描测试读取，Python 完整基线在同一基点的临时 detached clean worktree 中执行；该 worktree 不包含任何既有未跟踪文件。所有结论均保留真实失败，不做占位或弱化断言。

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Python 依赖 | `python -m pip check` | PASS：No broken requirements found |
| Python 全量单测 | `python -m unittest discover -s tests` | FAIL：692 tests，2 failures，5 skipped |
| 公开安全扫描 | `python scripts/security_check.py` | PASS |
| 产品事实 | `python scripts/check_product_facts.py` | PASS |
| 文本编码 | `python scripts/check_text_encoding.py` | PASS |
| Preflight | `python scripts/starbridge_preflight.py --markdown` | PASS：5 个 gate 全部通过 |
| 脱敏桥状态 | `python examples/bridge_status.py --json --redact-paths --soft-exit` | PASS（桌面软件未配置项按状态返回，不崩溃） |
| MCP safe-only | `python -m starbridge_mcp.server tools --json --safe-only` | PASS |
| 前端测试 | `npm test --prefix apps/starbridge-desktop` | PASS：4 files，27 tests |
| 前端构建 | `npm run build --prefix apps/starbridge-desktop` | PASS |
| Rust/Tauri | `cargo test --manifest-path apps/starbridge-desktop/src-tauri/Cargo.toml` | FAIL：Tauri build script 找不到 macOS sidecar |
| 桌面启动探针 | `npm run tauri:dev --prefix apps/starbridge-desktop` | FAIL：`beforeDevCommand` 仍调用 Windows-only `npm.cmd` |

### 基线数量复核

阶段 0 独立验收时，共享 dirty checkout 中的测试计数与报告不一致。为排除既有未跟踪 macOS 交接材料影响，总控随后在候选提交的 detached clean worktree 中，使用同一项目 Python 3.12 环境并允许 localhost 测试套接字，重新执行：

```bash
PYTHONDONTWRITEBYTECODE=1 "$PROJECT_VENV/bin/python" -m unittest discover -s tests
```

其中 `PROJECT_VENV` 指向本阶段创建的项目 `.venv`；测试工作目录为候选提交的 detached clean worktree。

复核结果仍为 **692 tests、2 failures、5 skipped、0 errors**，与本报告原始基线一致。原始完整输出只保存在本机临时证据目录，不进入公开仓库；报告正文不记录本机绝对路径。

## 原生失败与阻塞

1. **Python 全量单测仍有 2 个仓库原生失败。**
   - `test_export_script_refuses_without_confirmations`：测试期待固定拒绝文案，但当前 PowerShell 脚本返回的是结构化 dry-run warning，测试与实现契约不一致。
   - `test_confirmed_recipe_records_redacted_evidence`：Photoshop color preprocess 的 manifest 在 `redacted_paths` 中仍保留仓库绝对路径。该项具有路径脱敏风险，不能标绿。
2. **Rust/Tauri 无法进入测试执行。** `tauri-build` 要求 `apps/starbridge-desktop/src-tauri/binaries/starbridge-sidecar-aarch64-apple-darwin`，公开 main 未提供或构建该原生 sidecar；未创建空占位文件。
3. **Tauri dev 不能在 macOS 启动。** `tauri.conf.json` 的 `beforeDevCommand` 是 `npm.cmd run dev`，macOS 返回 `npm.cmd: command not found`。
4. **当前 workflow 没有 macOS runner。** `.github/workflows/ci.yml` 的 Python/前端覆盖 Ubuntu/Windows，Rust/Tauri 仅在 Windows job 中通过创建 Windows 测试资源运行。
5. **CodeGraph 能力缺口。** 当前项目未注册且无 CodeGraph tool；进入阶段 1 业务/适配代码前应由总控决定是否注册。

## Git 与 GitHub Actions 基线

- 起始 tracked worktree 与 index 均 clean；`main` 与本地 `origin/main` 同为基点 `2eecfe3e...`。
- remotes：`origin` 指向 `Rabbitgenius-rgb/CreNexus`，`upstream` 指向 `jianbaorui07-dot/CreNexus`。
- `origin` 的 `main` 查询不到现有 Actions run；需在本分支首次 push 后确认该仓库是否启用 Actions。
- `upstream` 同一基点的 CI、CodeQL、Dependency Graph 最近结果均为 success；CI run：<https://github.com/jianbaorui07-dot/CreNexus/actions/runs/29646424226>。该成功只代表现有 Ubuntu/Windows 矩阵，不代表 macOS 通过。
- 本报告提交前分支尚未 push；push 后状态由阶段 0 最终汇报补充，不能预写为绿色。

## 回滚点

- 安全回滚基点：`2eecfe3e52be78ef79327b4f0ce34bc81dcc2503`。
- 阶段 0 计划仅提交 `handoff/test-report.md`。如需撤销，应对阶段 0 提交执行 `git revert`；不要对共享 checkout 使用 `reset`、`clean` 或 `stash`。

## 阶段 0 结论

环境依赖已补齐到可运行基线，Python/MCP 安全检查和前端测试/构建通过；但 Python 全量单测存在 2 个真实失败，Rust/Tauri 因缺少 darwin sidecar 失败，Tauri dev 因 `npm.cmd` 失败。阶段 0 只能认定为“基线已建立、阻塞已复现”，不能认定 macOS 软件已跑通。进入后续适配前需要独立验收本报告与证据边界。

## 阶段 0.5：恢复 Python 基线

- 日期：2026-07-22（Asia/Shanghai）
- 范围：只修复阶段 0 记录的两个 Python 基线失败；未开始阶段 1，未处理 Darwin sidecar 或 Tauri `npm.cmd`。
- CodeGraph：本阶段已确认仓库登记有效，并在编辑前重建 evidence manifest 真实调用链、相关测试、依赖和变更影响。`sanitize_path()` 是 medium 影响的通用文本边界（128 个传递影响点）；`evidence.py::sanitize_path_string()` 仅处理 evidence 字段中已确定的路径值，影响为 low（12 个传递影响点）。所有 CodeGraph 命中路径均在本仓库内。

### 根因与修改

1. `camera_raw_export.ps1` 的未确认分支已返回结构化拒绝结果，但 warning 文案漂移，缺少测试和公开契约要求的稳定拒绝语义。现统一为明确的 `Refusing Camera Raw export without explicit confirmation`，并继续声明 `-ConfirmApply` 与 `-ConfirmExport` 都是必需条件。
2. 原失败不是任意文本或 URI 脱敏问题。`create_manifest()` 把 `ensure_evidence_path()` 返回的已解析文件系统路径交给 `evidence.py::sanitize_path_string()`，clean worktree 位于 macOS 临时根时，该结构化路径原样进入 `redacted_paths`。第三次返工已撤销阶段 0.5 对通用 `security.py` 引入的 URI、query/fragment 和 percent-encoding 解析，将通用 sanitizer 完整恢复到阶段 0 基准。evidence 模块的结构化 path helper 仅对以 `/` 开头的 POSIX 路径做判定用词法规范化：折叠重复 `/`，不 `resolve`、不访问文件系统，也不改写非敏感输出。规范化后命中 `/tmp`、`/private/tmp`、`/var/tmp`、`/private/var/tmp`、`/var/folders` 或 `/private/var/folders` 根值及其子路径时，整值返回 `<REDACTED_PATH>`；相似根、相对路径和带 scheme 的 HTTP/`file:` URI-like 字符串不由该 helper 扩展解析。

### 验证证据

为隔离既有未跟踪文件，全量测试仍在候选基点的临时 detached clean worktree 中执行，并把本阶段未提交 diff 应用到该 worktree。命令中的 `PROJECT_VENV` 和 `CLEAN_WORKTREE` 仅代表本机临时运行位置，报告不记录其绝对路径。

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 两个原失败 + sanitizer/evidence 相关测试 | `PYTHONDONTWRITEBYTECODE=1 "$PROJECT_VENV/bin/python" -m unittest -v tests.test_photoshop_camera_raw_protocol.PhotoshopCameraRawProtocolTests.test_export_script_refuses_without_confirmations tests.test_photoshop_color_preprocess.PhotoshopColorPreprocessTests.test_confirmed_recipe_records_redacted_evidence tests.test_security_sanitizer tests.test_evidence_manifest` | PASS：14 tests |
| Python clean-worktree 全量 | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$CLEAN_WORKTREE" "$PROJECT_VENV/bin/python" -m unittest discover -s tests` | PASS：695 tests，5 skipped |
| Python lint | `"$PROJECT_VENV/bin/python" -m ruff check starbridge_mcp/core/evidence.py starbridge_mcp/core/security.py tests/test_evidence_manifest.py tests/test_security_sanitizer.py` | PASS |
| Diff 完整性 | `git diff --check` | PASS |
| 公开安全扫描 | `PYTHONDONTWRITEBYTECODE=1 "$PROJECT_VENV/bin/python" scripts/security_check.py` | PASS |
| 文本编码 | `PYTHONDONTWRITEBYTECODE=1 "$PROJECT_VENV/bin/python" scripts/check_text_encoding.py` | PASS |
| Clean preflight | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$CLEAN_WORKTREE" "$PROJECT_VENV/bin/python" scripts/starbridge_preflight.py --markdown` | PASS：5 checks |

第一次 clean-worktree 全量运行未设置 `PYTHONPATH="$CLEAN_WORKTREE"`，导致一个 subprocess 从项目 `.venv` 的 editable 安装位置解析源码并报 `ModuleNotFoundError`；这不是仓库代码失败。补齐与 clean worktree 一致的源码根后，全量结果如上恢复绿色。localhost/socket 测试按权限流程在非沙箱环境运行，没有把 sandbox 的 `PermissionError` 计为代码失败。

共享 dirty checkout 额外运行 `starbridge_preflight.py --markdown` 时，`markdown_links` 因既有未跟踪根目录 `SKILL.md` 引用不存在的 `references/compatibility.md` 而失败；该文件不属于本阶段，也未被修改或纳入提交。相同候选在不包含既有未跟踪文件的 clean worktree 中，完整 Python 套件所覆盖的 preflight 契约通过。

### 剩余风险与边界

- 当前 macOS 环境没有运行 Windows PowerShell、Photoshop COM 或真实 Camera Raw 导出；拒绝分支在本机走静态契约检查。真实 Windows 桌面软件行为仍需后续专用环境验证。
- 阶段 0 已记录的 Darwin sidecar、Tauri `npm.cmd` 和 macOS workflow 缺口均未在阶段 0.5 处理，状态不变。
- 本阶段候选仍需独立验收线程复核 diff、敏感信息、测试证据、提交范围及 local/remote SHA；实现线程不自批。
