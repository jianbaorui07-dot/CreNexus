# Windows 收费发布门槛

状态：**未达到收费发布条件。** 当前 NSIS 安装包未签名；本机安装验证不能替代干净机器、Defender 或 SmartScreen 验收。

软件内 GitHub Release 检查、显式确认、下载进度、Tauri 强制验签和 sidecar 安全关闭链路已经进入源码，但开发构建未配置正式更新公钥，当前没有可消费的 `latest.json`。详见 [SOFTWARE_UPDATE_CHANNEL.md](SOFTWARE_UPDATE_CHANNEL.md)。

## 分发与签名方案比较

| 方案 | 签名责任 | 适合场景 | 当前结论 |
| --- | --- | --- | --- |
| Microsoft Store + MSIX | Store 审核后为 MSIX/AppX 重签；无需自购 CA 证书 | 希望获得商店分发、统一信任与较少下载警告 | 候选；仍需验证 Tauri/sidecar/MSIX 生命周期与商店规则 |
| 传统 OV Authenticode | 购买 CA 颁发的组织验证证书，使用 SignTool 与 RFC 3161 时间戳 | 继续直接分发 NSIS/EXE | 可行；证书、主体、私钥硬件保护和声誉积累尚未落实 |
| Azure Artifact Signing（原 Trusted Signing） | Microsoft 托管短期证书与身份验证，可接 GitHub Actions/CI | 非商店分发但不自行保管导出式 PFX | 优先评估；先核对销售主体和地区资格 |
| NSIS 外部分发 | 发行方必须签安装器及其 PE 文件 | 保留当前安装体验和离线安装 | 只有完成 Authenticode 与全矩阵验收后才可公开收费 |

Microsoft 官方说明：Store 分发的 MSIX 由 Store 重签，但 MSI/EXE 不会被重签；非 Store 分发仍需可信代码签名。官方还说明即使使用有效 OV/EV 证书，新文件也可能在声誉建立前出现 SmartScreen 提示。因此“已签名”不等于“首次下载无警告”。

参考：

- [Code signing options for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Sign an MSIX package](https://learn.microsoft.com/en-us/windows/msix/package/signing-package-overview)
- [Sign your MSIX package: end-to-end guide](https://learn.microsoft.com/en-us/windows/msix/package/sign-msix-package-guide)
- [SmartScreen reputation for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
- [Microsoft Defender SmartScreen overview](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/)

自签名证书只允许本地开发或受控测试，不推荐也不接受为公众收费分发方案。

## 签名清单

正式候选必须记录并验证：证书主体、发行主体、证书用途、签名工具版本、RFC 3161 时间戳服务、SHA-256 文件哈希、安装器签名、主程序签名、Python sidecar 签名、随包 DLL/EXE 签名、签名验证输出、证书续期时间、私钥保护方式和 CI 秘密管理责任人。

私钥优先使用受管签名服务或硬件保护；不得把 PFX、口令、访问令牌或生产私钥提交到 Git、写入普通日志或放进安装包。CI 只获取最小权限的短期身份，签名步骤与普通构建步骤分离。

## 干净 Windows 验收矩阵

每个正式候选都必须保存脱敏证据，且不得把测试用户路径、授权文件或素材提交到仓库：

- Windows 11 x64 干净虚拟机；Windows 10 x64 仅在决定支持后加入；
- 非管理员账户、中文用户名、含空格安装/素材路径、完全离线网络；
- 安装、第一次启动、第二次启动、普通图片导入和真实 Community 矢量化；
- Community 无授权运行、无效授权拒绝、正确 Pro 授权（商业候选才执行）；
- 关闭、loopback 端口释放、无残留进程；
- 升级、失败回滚、卸载、用户数据保留、显式完全清除选项；
- Defender 全扫描、SmartScreen 首次下载体验、签名链与时间戳验证；
- 防火墙/抓包证明核心离线流程没有未说明的公网请求。

## 当前事实

| 门槛 | 状态 |
| --- | --- |
| 当前用户 NSIS 本机安装/首次与二次启动/关闭/卸载 | 2026-07-18 当前候选通过；用户数据保留，进程和端口无残留 |
| Authenticode | 未完成（`NotSigned`） |
| 安装器、主程序、sidecar、DLL 全签名 | 未完成 |
| 软件内更新代码与固定 GitHub Release 地址 | 已实现并通过前端/Rust 构建测试；正式签名通道未启用 |
| Tauri 更新私钥、公钥、`.sig` 与 `latest.json` | 未完成；私钥未创建、未进入仓库 |
| 签名发布 GitHub Actions | 已建立 fail-closed 工作流；因签名身份和受保护配置缺失而不可发布 |
| Windows 11 干净虚拟机 | 未完成 |
| Defender | 当前未签名 NSIS 候选已完成本机自定义扫描且检出 0；干净机完整矩阵仍未完成 |
| SmartScreen | 未完成 |
| 本机网络边界 | 首次与二次启动观察到 0 个公网 TCP 连接；sidecar 仅监听随机 `127.0.0.1` 端口 |
| 正式协议、隐私、退款、解绑与税务 | 未完成 |
| 公开下载与收费发布 | 未签名内部预览已通过 GitHub prerelease 开放给团队测试；正式签名版与收费发布未开放 |

结论：只能继续开发和内部验收，不得创建正式收费 Release。
