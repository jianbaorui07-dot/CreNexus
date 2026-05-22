# Codex 接入绘画工具项目路线图

更新时间：2026-05-22

这份文档把“Codex 接入任何绘画工具”的项目先收束成可执行路线。这里的绘画工具不只指传统画板，也包括图像生成、修图、设计稿、三维建模和工程制图工具。原则是：先稳定本机已经实践过的 ComfyUI、Blender、CAD、Photoshop 四条桥，再评估 Penpot/Figma、Krita 等扩展工具。

## 本机现状

| 通道 | 当前入口 | 当前状态 | 下一步 |
| --- | --- | --- | --- |
| Codex x ComfyUI | `examples/comfy_bridge/`；`COMFY_LAUNCHER` | 已有 API 示例和启动脚本配置方式；不在仓库记录本机路径 | 启动 ComfyUI 后跑 `python examples\bridge_status.py --json` 和 `python examples\comfy_bridge\comfy_probe.py` |
| Codex x Blender | `BLENDER_EXE`；`BLENDER_MCP_DIR` | 通过环境变量或常见安装路径识别 Blender 和 MCP 桥 | 用状态脚本固化检测路径，再补公开安全的 Blender 示例脚本 |
| Codex x CAD | `cad-mcp-autocad/`；`AUTOCAD_MCP_SETUP.md` | 状态检查已能找到 AutoCAD 2026 和 `pywin32/win32com` | 继续保留在 `cad-mcp-autocad/` 子项目内优化 |
| Codex x Photoshop | `examples/photoshop_bridge/`；`docs/photoshop-codex-bridge.md` | 已验证 Windows COM + Photoshop JavaScript 能创建测试文档、导出 PNG，并能调用主体选择做抠图实验 | 继续优化 UXP 面板、本地桥状态接口和 MCP 封装；不记录个人路径和素材信息 |
| 下载/整理 | `STARBRIDGE_DOWNLOAD_INBOX` | 下载目录只保存在本机环境变量里 | 如果要下载源码或安装包，先放本机收件箱，不直接塞进 Git 工作区 |

## 仓库入口

| 文件或目录 | 用途 |
| --- | --- |
| `docs/starbridge-link-protocol.md` | 星桥三联主协议：ComfyUI、Blender、CAD、Photoshop 四条桥的边界和安全规则 |
| `docs/01-codex-cad.md` | Codex 接入 CAD 中文介绍 |
| `docs/02-codex-comfyui.md` | Codex 接入 ComfyUI 中文介绍 |
| `docs/03-codex-photoshop.md` | Codex 接入 Photoshop 中文介绍 |
| `docs/04-codex-blender.md` | Codex 接入 Blender 中文介绍 |
| `docs/photoshop-codex-bridge.md` | Photoshop 本地桥接入方案、实验结论和安全边界 |
| `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop 的本机可用性 |
| `examples/comfy_bridge/README.md` | ComfyUI API 示例说明 |
| `examples/comfy_bridge/comfy_probe.py` | 只读读取 ComfyUI 状态、设备和 checkpoint |
| `examples/comfy_bridge/run_txt2img.py` | 提交基础文生图 workflow |
| `cad-mcp-autocad/` | AutoCAD MCP 子项目 |
| `examples/photoshop_bridge/` | Photoshop COM 探针和主体抠图实验脚本 |
| `scripts/draw_*.py` | 直接用 AutoCAD COM 绘制示例图纸 |

## 外部项目候选

| 工具方向 | 候选项目 | 可借鉴点 | 风险和前置条件 |
| --- | --- | --- | --- |
| ComfyUI 原生图像生成 | `Comfy-Org/ComfyUI` | 本机图像生成引擎，适合继续作为第一优先级 | 需要本机 ComfyUI 正在运行；模型和输出不进 Git |
| ComfyUI MCP | `artokun/comfyui-mcp` | 提供 workflow 执行、可视化、模型管理、调试、ControlNet/IP-Adapter 等 MCP 工具思路 | Node.js 版本、自动下载模型、token 和外部 API 要谨慎隔离 |
| ComfyUI MCP 轻量方案 | `alecc08/comfyui-mcp`、`joenorton/comfyui-mcp-server` | 可以对比轻量 MCP API 设计，避免一次引入过重依赖 | 需要先看维护状态和依赖边界 |
| Blender MCP | `djeada/blender-mcp-server`、`loonghao/dcc-mcp-blender` | Blender add-on + MCP server 的结构可参考，用于场景、材质、渲染、导出 | 需要 Blender 打开或 headless 运行；私有 `.blend`、贴图和资产不上传 |
| CAD MCP | `daobataotie/CAD-MCP` | 当前本地子项目来源，适合继续按 Windows COM/AutoCAD 路线优化 | 依赖 Windows、AutoCAD、pywin32；客户 DWG 不上传 |
| 设计稿/矢量设计 | `penpot/penpot-mcp`、Figma 官方 MCP 文档 | 适合从设计稿读取上下文、创建或修改设计元素 | Penpot/Figma 可能涉及账号、浏览器授权或团队席位，需要人工处理登录 |
| Photoshop 修图 | `examples/photoshop_bridge/`、Adobe UXP、`StarBoze/Photoshop-MCP-Server` | Windows COM + Photoshop JavaScript 可做最小接入；UXP 适合做面板；MCP 适合后续工具化 | 需要已授权 Photoshop；安装路径、PSD、素材路径、账号和授权信息不进 Git |
| Krita/其他画板 | 待二次筛选 | 适合作为开源绘画软件扩展方向 | 先找稳定插件/API，再决定是否下载 |

## 当前优化顺序

1. 先把本机状态检测做准：ComfyUI 根目录、ComfyUI 启动脚本、Blender 可执行文件、Blender MCP 桥、AutoCAD 路径都要能被 `examples/bridge_status.py` 识别。
2. 再增强 ComfyUI 示例：保留现有 `txt2img`，后续增加 `img2img`、upscale、inpaint、批量 prompt 和 workflow 校验。
3. 再把 ComfyUI 调用封装成更稳定的本地工具层：先用现有 HTTP API 脚本跑通，不急着引入完整第三方 MCP 包。
4. Blender 侧优先做公开安全示例：生成简单场景、材质、相机、渲染路径，不引用私有资产库。
5. CAD 侧继续走子项目隔离：所有 AutoCAD MCP 修改留在 `cad-mcp-autocad/`，根目录只更新说明。
6. Photoshop 侧先保留 COM 探针和主体抠图实验，继续评估 UXP 面板和本地 MCP 封装；所有输入图和输出图都由参数传入，不写入仓库。
7. Penpot/Figma 等扩展工具先做评估表和最小探针；凡是需要登录、订阅、浏览器授权、验证码或账号审批的步骤，都停下来让人手动处理。

## 下载和安全规则

如果确实需要下载源码、安装包或调研资料，先放到：

```text
%STARBRIDGE_DOWNLOAD_INBOX%
```

建议源码克隆位置：

```text
%STARBRIDGE_DOWNLOAD_INBOX%\codex\GitHub项目源码_保持可运行
```

不要下载或提交以下内容：

- 密码、token、Cookie、OAuth 缓存、浏览器资料。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成输出。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存。
- CAD 客户图纸、DWG 输出、授权文件。
- Photoshop 安装路径、Creative Cloud 缓存、PSD 私有工程、商业素材、源图路径和导出结果。

## 调研来源

- ComfyUI: https://github.com/Comfy-Org/ComfyUI
- ComfyUI MCP: https://github.com/artokun/comfyui-mcp
- ComfyUI MCP examples: https://github.com/alecc08/comfyui-mcp, https://github.com/joenorton/comfyui-mcp-server
- Blender MCP: https://github.com/djeada/blender-mcp-server, https://github.com/loonghao/dcc-mcp-blender
- CAD MCP: https://github.com/daobataotie/CAD-MCP
- Penpot MCP: https://github.com/penpot/penpot-mcp
- Figma MCP official guide: https://help.figma.com/hc/en-us/articles/32132100833559-Guide-to-the-Figma-MCP-server
- Photoshop UXP official docs: https://developer.adobe.com/photoshop/uxp/
- Photoshop UXP scripting: https://developer.adobe.com/photoshop/uxp/ps_reference/media/uxpscripting/
- Photoshop MCP: https://github.com/StarBoze/Photoshop-MCP-Server
