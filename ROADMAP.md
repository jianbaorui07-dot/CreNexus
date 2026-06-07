# Roadmap

本路线图记录 StarBridge 公开仓库的下一步方向。当前项目定位是 **Codex Computer Use + StarBridge MCP + Safety Verification Layer**：Computer Use 负责 GUI 观察和复现，MCP tools 负责结构化生产操作，Safety layer 负责脱敏、权限边界和发布前验证。

## v0.1.0

- Adobe sandbox demo bridge
- Safe MCP tool registration
- Local output isolation
- Smoke test documentation
- Release notes draft

## v0.2.0

- EvidenceManifest: 统一记录 plan、job、output files、screenshots、validation、warnings、safety decision。
- JobStatus: 统一使用 `queued / running / completed / failed / cancelled / needs_user` 状态词汇。
- visual evidence: 只保存脱敏截图和输出摘要到 `examples/output/evidence/`。
- dry-run validation: `evidence --validate`、`job-status` 和 safe-only registry 都必须可在 CI 运行。
- ComfyUI real txt2img closed loop: 保持真实生成在本机显式确认后执行，同时把生命周期摘要接到统一 evidence 层。

## High Priority

| 任务 | 目标 | 验收标准 |
| --- | --- | --- |
| Computer Use integration guidance | 补清楚 GUI Computer Use 与 StarBridge MCP 的分工、安全等级和各软件双通道流程 | README 链接到 `docs/07-codex-computer-use.md` 和 `docs/computer-use-vs-mcp.md` |
| post-GUI verification commands | 每次 GUI 观察或复现后，给出可重复的 CLI / MCP 验证命令 | 文档示例统一引用 `npm.cmd test`、`npm.cmd run preflight`、`bridge_status.py --redact-paths` |
| visual evidence + redacted report | GUI 截图和复现说明只作为脱敏证据，不提交客户素材或私有输出 | 报告不包含真实路径、账号、token、模型路径、素材路径或授权信息 |
| StarBridge MCP tool hardening | 保持 `status`、`probe`、tool registry 和 DXF plan 工具稳定 | `npm.cmd test` 和 `npm.cmd run preflight` 通过 |
| Safety verification layer | 强化路径脱敏、只读检查、dry-run、发布前体检和 forbidden content 扫描 | preflight 输出可审查，失败信息给出明确修复方向 |

## ComfyUI

| 状态 | 任务 | 目标 | 验收标准 |
| --- | --- | --- | --- |
| 完成 | v0.2.0 ComfyUI txt2img closed loop | 当前已补最小闭环：读取 `STARBRIDGE_COMFYUI_URL`、校验 workflow、提交 `/prompt`、查询 `/history/{prompt_id}`、生成脱敏 `examples/output/comfyui/demo_manifest.json` | manifest 只含 workflow 文件名、prompt hash、job status、输出数量和输出 basename；真实图片、模型名、本机路径不提交 |
| 完成 | ComfyUI safe workflow loop | 已增强 `workflow_validate` 结构化报告，并为 `img2img`、`inpaint`、`upscale` 增加 plan-only dry-run 示例 | 不读取真实图片、模型目录或 output；不调用 `/prompt`；测试覆盖非法 JSON、缺字段和路径脱敏 |
| 完成 | ComfyUI workflow draft builder | 已新增 `comfy.workflow_draft`，可生成 `txt2img`、`img2img`、`inpaint`、`upscale` 的 API-like workflow 草案 | 草案包含 metadata，使用 placeholder model/assets，通过 `workflow_validate`，不读文件系统、不联网、不 submit |
| 完成 | ComfyUI workflow graph composer | 已新增 `comfy.workflow_compose`，可把 checkpoint、prompt、latent/image、sampler、decode/save、upscale、inpaint mask 等安全模块组合成 workflow graph | composed workflow 通过 `workflow_validate`，节点 id 不重复，metadata 含 `draft=true` 或 `safe_placeholder=true`，不读文件系统、不联网、不 submit |
| 完成 | ComfyUI workflow template registry | 已新增 `workflow_template_registry`，注册 `txt2img`、`img2img`、`inpaint`、`upscale` 和 `complex_creative_poster` 公开模板 | 模板 lint 检查唯一 id、version、composer modules、required inputs、forbidden pattern 和 validation status；MCP tools 全部 safe read-only，不读私有文件、不联网、不 submit |
| 计划 | CLI / npm shortcuts | 为 template list/get/from-template 增加更短的本地验证入口 | 命令只调用本地 JSON 生成和校验，不 submit queue |
| 计划 | job / asset lifecycle summary | 为已审查 workflow 增加脱敏 job / asset 生命周期摘要 | 不提交模型、LoRA、VAE、ControlNet 或生成图；真实队列调用必须显式确认 |
| 计划 | workflow lint / repair | 扩展 workflow lint 和可审查 repair 报告 | 只处理传入 JSON 或公开示例，不扫描私有目录 |
| 计划 | local ComfyUI probe gate | 为需要本机服务的流程增加明确 probe gate | ComfyUI 缺失时 soft-exit，不阻塞 CI |
| 计划 | dry-run queue payload | 生成可审查的 queue payload dry-run 摘要 | 默认不请求 `/prompt`，不读取 output |
| 计划 | user-confirmed submit gate | 将真实 submit 保持在用户确认后的本机流程中 | 必须显式确认，并继续脱敏 manifest 和输出 basename |

## Other Bridges

| 任务 | 目标 | 验收标准 |
| --- | --- | --- |
| Photoshop structured tools | 把 `document_info`、受保护导出和报告摘要继续收敛成安全 MCP 工具 | 写入类动作需要确认，路径必须参数传入 |
| Illustrator read-only preflight | 增加画板、链接资源、颜色模式和导出风险摘要 | 不打开客户 `.ai`，不输出源素材路径 |
| Blender sandbox scene demo | 增加公开安全的基础场景生成脚本和 render proof | 不打开私有 `.blend`，不执行任意 Python，渲染输出放在忽略目录 |
| CapCut / Jianying draft probe | 继续只读草稿结构研究，不读取私有草稿内容 | 不自动导出视频，不操作账号或会员能力 |
| CAD plan schema | 给 CAD 增加更清楚的 JSON 参数格式和标准零件示例 | plan validate、dry-run 和 guarded write 继续通过 CI |

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
