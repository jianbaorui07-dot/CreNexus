# StarBridge 文档入口

本目录同时包含当前实现说明、软件桥专题、实验记录和历史研究。产品化升级期间，以本页列出的“当前事实来源”为准；P2 会把普通用户文档与开发者参考进一步拆分，但不会复制同一段能力说明到多个文件。

## 当前事实来源

| 主题 | 文档 |
| --- | --- |
| P0 产品化审计与分阶段计划 | [PRODUCTIZATION_AUDIT.md](PRODUCTIZATION_AUDIT.md) |
| 能力状态与证据边界 | [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) |
| 本地 HTTP API | [starbridge-backend.md](starbridge-backend.md) |
| MCP 本地配置 | [local-mcp-setup.md](local-mcp-setup.md) |
| Windows 开发环境 | [windows-install.md](windows-install.md) |
| Community / Pro 离线商业化边界 | [OFFLINE_COMMERCIALIZATION.md](OFFLINE_COMMERCIALIZATION.md) |
| 矢量化模式 | [vectorization-modes.md](vectorization-modes.md) |
| 精确像素矢量路线 | [exact-pixel-vectorization.md](exact-pixel-vectorization.md) |
| 安全披露与仓库边界 | [../SECURITY.md](../SECURITY.md) / [../AGENTS.md](../AGENTS.md) |

## 统一术语

- **MCP**：让 AI 以结构化方式调用外部工具的协议。
- **dry-run**：只生成执行计划，不真正修改文件。
- **sidecar**：跟随桌面软件一起运行的本地后台程序。
- **UXP**：Adobe 用于开发 Photoshop 和 Illustrator 插件的平台。
- **Evidence（证据摘要）**：记录任务计划、运行状态、输出、截图或摘要、验证结果和安全决定。
- **sandbox（安全目录）**：限制程序读写范围的受控目录。

## 目标文档结构（P2）

| 文件 | 单一职责 |
| --- | --- |
| `QUICK_START.md` | 普通用户、Codex/MCP 用户和开发者三条最短开始路径 |
| `USER_GUIDE.md` | 桌面产品日常使用 |
| `DESKTOP_APP.md` | 桌面架构、sidecar 和生命周期 |
| `SOFTWARE_SUPPORT.md` | 各软件状态、证据和限制 |
| `WORKFLOW_GUIDE.md` | 以用户目标命名的工作流 |
| `ARCHITECTURE.md` | 系统边界与组件关系 |
| `MCP_REFERENCE.md` | MCP tools、resources、prompts 参考 |
| `SAFETY_MODEL.md` | local-first、确认门、safe roots、脱敏和威胁模型 |
| `TROUBLESHOOTING.md` | 普通语言故障排查与技术详情 |
| `DEVELOPMENT.md` | 开发环境、测试和贡献流程 |
| `RELEASE_GUIDE.md` | 构建、签名、安装器和发布验证 |

这些目标文件在 P2 建立后，应引用能力矩阵和统一文案常量，不复制状态表形成第二份事实来源。
