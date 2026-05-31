# Roadmap

本路线图记录 StarBridge 公开仓库的下一步方向。当前项目定位是 **Codex Computer Use + StarBridge MCP + Safety Verification Layer**：Computer Use 负责 GUI 观察和复现，MCP tools 负责结构化生产操作，Safety layer 负责脱敏、权限边界和发布前验证。

## High Priority

| 任务 | 目标 | 验收标准 |
| --- | --- | --- |
| Computer Use integration guidance | 补清楚 GUI Computer Use 与 StarBridge MCP 的分工、安全等级和各软件双通道流程 | README 链接到 `docs/07-codex-computer-use.md` 和 `docs/computer-use-vs-mcp.md` |
| post-GUI verification commands | 每次 GUI 观察或复现后，给出可重复的 CLI / MCP 验证命令 | 文档示例统一引用 `npm.cmd test`、`npm.cmd run preflight`、`bridge_status.py --redact-paths` |
| visual evidence + redacted report | GUI 截图和复现说明只作为脱敏证据，不提交客户素材或私有输出 | 报告不包含真实路径、账号、token、模型路径、素材路径或授权信息 |
| StarBridge MCP tool hardening | 保持 `status`、`probe`、tool registry 和 DXF plan 工具稳定 | `npm.cmd test` 和 `npm.cmd run preflight` 通过 |
| Safety verification layer | 强化路径脱敏、只读检查、dry-run、发布前体检和 forbidden content 扫描 | preflight 输出可审查，失败信息给出明确修复方向 |

## Medium Priority

| 任务 | 目标 | 验收标准 |
| --- | --- | --- |
| v0.2.0 ComfyUI txt2img closed loop | 当前已补最小闭环：读取 `STARBRIDGE_COMFYUI_URL`、校验 workflow、提交 `/prompt`、查询 `/history/{prompt_id}`、生成脱敏 `examples/output/comfyui/demo_manifest.json` | manifest 只含 workflow 文件名、prompt hash、job status、输出数量和输出 basename；真实图片、模型名、本机路径不提交 |
| Photoshop structured tools | 把 `document_info`、受保护导出和报告摘要继续收敛成安全 MCP 工具 | 写入类动作需要确认，路径必须参数传入 |
| Illustrator read-only preflight | 增加画板、链接资源、颜色模式和导出风险摘要 | 不打开客户 `.ai`，不输出源素材路径 |
| Blender scene summary | 增加安全 scene / render 摘要，避免任意 Python 执行 | 默认只读，渲染输出放在忽略目录 |
| ComfyUI workflow lifecycle | 补 `img2img`、inpaint、upscale 和 job / asset 生命周期摘要 | 不提交模型、LoRA、VAE、ControlNet 或生成图 |
| CapCut / Jianying draft probe | 继续只读草稿结构研究，不读取私有草稿内容 | 不自动导出视频，不操作账号或会员能力 |

## Blocked By Design

以下方向不进入自动化路线图：

- 自动登录、创建账号、输入密码、验证码、OTP 或 token。
- 自动支付、订阅、购买、退款或保存支付方式。
- 上传客户素材、商业图纸、私有 `.blend`、PSD、AI、DWG、视频草稿或模型。
- 删除本机或云端文件。
- 修改 Windows、浏览器、Creative Cloud 或软件授权相关安全设置。
- 绕过验证码、付费墙、授权检查或安全拦截。

## Verification

发布前至少运行：

```powershell
npm.cmd test
npm.cmd run preflight
python examples\bridge_status.py --json --redact-paths --soft-exit
```

需要真实桌面软件参与时，先用 Computer Use 做 L0 观察，再把可重复部分迁移到 CLI / MCP 工具验证。
