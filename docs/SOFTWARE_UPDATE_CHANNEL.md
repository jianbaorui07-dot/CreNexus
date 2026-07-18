# StarBridge 软件更新通道

状态：**软件内更新链路已实现，但正式通道尚未启用。** 当前只有 unsigned internal preview，仍缺少受信任的 Windows 代码签名身份、生产更新签名密钥和首个通过发布门禁的签名 GitHub Release，因此不能声称用户已经可以自动更新。

## 用户体验

正式签名构建的稳定版按以下流程工作：

1. StarBridge 启动约 2.5 秒后检查一次正式版本；应用持续运行时每 4 小时检查一次。
2. 用户可以在“设置与诊断 → 软件更新”关闭定时检查，或随时点击“立即检查更新”。
3. 顶部栏提供固定的“GitHub 项目”按钮，一键打开公开项目主页；地址由 Rust 固定白名单提供，前端不能传入任意 URL。
4. 检查只读取固定地址 `https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/releases/latest/download/latest.json`。
5. 发现更高的 SemVer 版本后，在顶部栏和软件更新页显示版本号与发布说明。
6. StarBridge 不自动下载。用户必须确认已经保存工作，才会开始下载。
7. Tauri 在安装前强制验证更新包签名；验证不能关闭。验证失败时保留当前版本。
8. 签名验证通过后，StarBridge 先请求本机 sidecar 正常关闭并释放 loopback 端口，再启动 NSIS 更新安装程序。Windows 安装阶段会关闭当前应用。

软件关闭时不运行后台更新服务。Community 的核心创作流程仍可完全离线使用；更新检查失败不会阻止启动、矢量化或读取本机任务。

## “GitHub 实时联动”的准确含义

普通 commit、PR 或未通过测试的 `main` 变更不会直接进入用户电脑。只有满足以下条件，已安装软件才会看到新版本：

- 版本号在 npm、Cargo、Tauri 配置和产品 Manifest 中完全一致；
- 发布 commit 已进入 `origin/main`；
- 创建 `starbridge-desktop-v<semver>` 标签；
- GitHub Actions 的 Python、前端、Rust、安全和打包测试全部通过；
- sidecar、主程序、安装器及需要发行方签名的 PE 文件通过 Authenticode；
- Tauri 生成并验证不可省略的更新签名；
- `latest.json` 只指向同一 GitHub Release 中的已验证安装器；
- `starbridge-release` GitHub Environment 的人工审批（应在仓库设置中配置）通过。

这使“项目持续优化 → 发布稳定版本 → 软件提示更新”成为自动化链路，同时避免把开发中的源码当成正式软件。

## 两套签名不是同一件事

| 签名 | 作用 | 私钥位置 |
| --- | --- | --- |
| Windows Authenticode | 让 Windows 验证发布者、文件完整性与时间戳 | 受管签名服务、硬件保护或受控 CI 证书；不得进入 Git |
| Tauri 更新签名 | 让已安装的 StarBridge 拒绝伪造或被替换的更新包 | GitHub Environment/Secrets 或更强的外部密钥保管；不得进入 Git |

更新公钥可以嵌入应用并公开；两个私钥都不能进入公开仓库、安装包、普通日志或前端 WebView。丢失 Tauri 更新私钥将导致已经安装的版本无法验证后续更新，因此必须先由产品所有者确定备份、访问和轮换责任人。

## GitHub 发布配置

工作流：`.github/workflows/starbridge-desktop-release.yml`。

必须先建立受保护的 `starbridge-release` Environment，并配置：

- Secret `STARBRIDGE_UPDATE_PUBLIC_KEY`；
- Secret `TAURI_SIGNING_PRIVATE_KEY`；
- Secret `TAURI_SIGNING_KEY_PASSPHRASE`（如密钥设有口令）；
- Secret `WINDOWS_SIGNING_CERTIFICATE_BASE64`；
- Secret `WINDOWS_SIGNING_CERTIFICATE_PASSPHRASE`；
- Variable `WINDOWS_SIGNING_SUBJECT`；
- Variable `WINDOWS_TIMESTAMP_URL`（使用证书服务商认可的 RFC 3161 服务）。

当前工作流为传统 OV PFX 路径准备。若产品所有者选择 Azure Artifact Signing、SignPath 或其他受管代码签名服务，应替换 Authenticode 步骤，保留版本一致性、测试、Tauri 更新签名、Manifest 校验和 Release 门禁。

## 尚未完成

- 未生成生产 Tauri 更新私钥；
- 未配置更新公钥；
- 未取得受信任 Authenticode 身份；
- 未配置受保护 GitHub Environment 或签名变量；
- 未生成正式 `latest.json`；
- 已创建不触发正式更新通道的未签名内部预览 prerelease；尚未创建可由更新器消费的正式签名 Release；
- 未在旧版本 → 新版本路径上完成真实升级、失败恢复和用户数据保留验证；
- 未完成干净 Windows、Defender 与 SmartScreen 验收；
- 尚未实现独立恢复点与一键回滚。

在这些门槛完成前，官网候选可以提供明确标注风险的未签名内部预览下载，但必须继续把正式签名稳定版和收费发布显示为未开放。

参考：

- [Tauri Updater](https://v2.tauri.app/plugin/updater/)
- [Tauri Windows code signing](https://v2.tauri.app/distribute/sign/windows/)
- [GitHub release assets](https://docs.github.com/en/rest/releases/assets)
- [Windows code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
