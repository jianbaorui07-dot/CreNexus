# 星桥三联：Codex 本地创意软件桥接 MVP

这是一个 **面向创意行业软件的 Codex 本地桥接实验框架**。它通过统一的安全规范、状态探测、示例脚本和桥接协议，让 Codex 能逐步调度 ComfyUI、CAD、Photoshop、Illustrator、Blender、剪映 / CapCut 等本地创作工具。

当前项目是 **Windows-first local bridge**，不是跨平台开箱即用工具，也不声称已经完整接入所有软件。仓库重点是把可公开协作的最小闭环做稳：状态表、探针、示例脚本、workflow、测试、CI 和安全检查。

## 核心分工

1. Codex 负责脚本生成、状态检测、流程调度、参数整理和日志记录。
2. 本地专业软件负责真正的生成、渲染、修图、矢量化、制图和剪辑。
3. 公开仓库只保存说明、协议、示例脚本、workflow 和安全检查。
4. 公开仓库不保存模型、素材、生成图、客户文件、账号、密钥或本机路径。
5. 所有真实安装路径、输出目录和私有资产路径都应通过本机环境变量或本地配置传入。

## 中文阅读指南

| 步骤 | 做什么 | 入口 |
| --- | --- | --- |
| 1 | 了解项目范围和安全边界 | 本页 README |
| 2 | 按目标选择软件桥 | [中文用途索引](docs/中文用途索引.md) |
| 3 | 查看桥接协议和状态规则 | [星桥链接协议](docs/starbridge-link-protocol.md) |
| 4 | 检查本机环境 | `npm.cmd run status:probe:json` |

## 软件桥当前状态表

| 软件桥 | 当前状态 | 已有能力 | 暂未完成 |
| --- | --- | --- | --- |
| ComfyUI | 已可运行，仍属 experimental | `comfy_probe.py` 只读探针；`run_txt2img.py` 文生图 API 示例；基础 txt2img workflow；workflow 节点和 checkpoint 校验 | `img2img`、inpaint、upscale、更多 workflow 校验、队列错误解析 |
| CAD / AutoCAD | 已可运行，仍属 experimental | AutoCAD MCP 子项目；状态探针；公开演示绘图脚本；CAD 自然语言解析测试 | 标准化导出、参数 JSON 契约、真实 AutoCAD 环境回归测试、文档细化 |
| Photoshop | 实验中 | 本机诊断、COM 探针、当前文档信息、主体抠图实验、接入报告 | 稳定生产级自动化工作流、批量 PSD、UXP 面板、MCP 工具封装 |
| Illustrator / AI 矢量文件 | 路线图阶段 | 接入说明；环境探测；`ILLUSTRATOR_EXE` 和 COM 可用性检查 | Image Trace、SVG/PDF/PNG 标准化导出、公开安全测试画板脚本 |
| Blender | 路线图阶段 | 接入说明；Blender 可执行文件和 MCP 目录探测 | 公开安全场景生成脚本、渲染闭环、Blender MCP 示例 |
| 剪映 / CapCut | research | 调研文档；本地草稿桥路线；可执行文件和草稿目录环境变量设计 | 稳定官方桌面 API 不存在；草稿写入、模板验证、自动导出都未完成 |

状态含义：

- `experimental`：有可运行脚本或探针，但仍需要本机软件和人工确认。
- `research`：以调研、许可、安全边界和路线验证为主。
- `planned`：已有说明或探测方向，但公开安全脚本尚未闭环。

## 统一命令入口

建议在 Windows PowerShell 里使用 `npm.cmd`，避免 PowerShell 拦截 `npm.ps1`。

| 类别 | 命令 | 作用 |
| --- | --- | --- |
| 状态类 | `npm.cmd run status:manifest` | 读取各软件桥 `bridge.json` 并输出 Markdown |
| 状态类 | `npm.cmd run status:manifest:json` | 读取各软件桥 `bridge.json` 并输出 JSON |
| 探测类 | `npm.cmd run status:probe` | 探测本机软件环境，会跳过或降级真实软件连接失败 |
| 探测类 | `npm.cmd run status:probe:json` | 以 JSON 输出本机环境探测结果 |
| 探测类 | `npm.cmd run comfy:probe` | 只读探测本机 ComfyUI API |
| 运行类 | `npm.cmd run comfy:txt2img -- --prompt "a quiet futuristic tea house" --ckpt "<checkpoint-name>"` | 提交 ComfyUI txt2img 任务 |
| 探测类 | `npm.cmd run photoshop:diagnose` | 运行 Photoshop 本机诊断 |
| 安全类 | `npm.cmd run security:check` | 检查禁止提交的资产类型和敏感路径 |
| 测试类 | `npm.cmd test` | 运行离线单元测试 |

直接使用 Python / PowerShell 也可以：

```powershell
python scripts\collect_bridge_status.py --json
python examples\bridge_status.py --json
python examples\comfy_bridge\comfy_probe.py
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house" --ckpt "<checkpoint-name>"
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
python scripts\security_check.py
python -m unittest discover -s tests
```

ComfyUI 文生图脚本不再默认选择第一个 checkpoint。没有显式 `--ckpt` 时会失败；只有加 `--allow-first-checkpoint` 才会使用 ComfyUI 返回的第一个模型。

## 仓库区域标注

| 区域 | 目录或文件 | 说明 |
| --- | --- | --- |
| 总览和协议 | `README.md`、`docs/中文介绍.md`、`docs/starbridge-link-protocol.md` | 项目定位、本地软件桥分工和公开边界 |
| 中文索引 | `docs/中文用途索引.md`、`docs/中文标注规范.md` | 中文导航和说明规范 |
| 状态 manifest | `examples/*_bridge/bridge.json` | 每条桥的统一状态、入口、支持任务和安全说明 |
| 状态检查 | `scripts/collect_bridge_status.py`、`examples/bridge_status.py` | manifest 汇总和本机环境探测 |
| 图像生成区 | `examples/comfy_bridge/` | ComfyUI API 探针、文生图脚本和 workflow JSON |
| 工程制图区 | `cad-mcp-autocad/`、`scripts/`、`examples/cad_bridge/` | AutoCAD MCP 子项目、状态探针和公开演示绘图脚本 |
| Photoshop 示例 | `examples/photoshop_bridge/` | COM 诊断、测试文档、主体抠图和本机报告 |
| AI 矢量文件桥 | `examples/illustrator_bridge/`、`docs/05-codex-illustrator.md` | Illustrator 环境探测、路线和安全边界 |
| Blender 桥 | `examples/blender_bridge/`、`docs/04-codex-blender.md` | Blender 探针和后续公开安全脚本入口 |
| 剪映 / CapCut 桥 | `examples/capcut_jianying_bridge/`、`docs/06-codex-jianying.md` | 草稿桥调研、探针和安全边界 |
| CI 和测试 | `.github/workflows/ci.yml`、`tests/` | Windows CI、schema、脚本路径、安全和离线逻辑测试 |

## 本地配置

真实路径不要写进 GitHub。每台电脑用环境变量或本地 `.env` 管理：

| 软件或目录 | 环境变量 |
| --- | --- |
| ComfyUI API 地址 | `STARBRIDGE_COMFYUI_URL` |
| ComfyUI 启动脚本 | `COMFY_LAUNCHER` 或 `COMFY_START_SCRIPT` |
| ComfyUI 根目录 | `COMFY_ROOT` 或 `COMFYUI_PATH` |
| ComfyUI 输出目录 | `COMFY_OUTPUT_DIR` |
| Blender 可执行文件 | `BLENDER_EXE` |
| Blender MCP 目录 | `BLENDER_MCP_DIR` |
| AutoCAD 可执行文件 | `AUTOCAD_EXE` |
| Photoshop 可执行文件 | `PHOTOSHOP_EXE` |
| Illustrator 可执行文件 | `ILLUSTRATOR_EXE` |
| 剪映可执行文件 | `JIANYING_EXE` |
| CapCut 可执行文件 | `CAPCUT_EXE` |
| 剪映草稿目录 | `JIANYING_DRAFTS_DIR` |
| CapCut 草稿目录 | `CAPCUT_DRAFTS_DIR` |
| 下载收件箱 | `STARBRIDGE_DOWNLOAD_INBOX` |

## 不发布内容

- 账号、密码、验证码、Cookie、token、OAuth 缓存、浏览器资料和支付信息。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成图片和输出目录。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存和本机插件缓存。
- CAD 客户图纸、商业 DWG、授权文件和真实项目输出。
- Photoshop 安装路径、Creative Cloud 缓存、PSD、商业字体、笔刷、购买素材、源图和导出结果。
- Illustrator 安装路径、Creative Cloud 缓存、AI 私有工程、商业字体、商业画笔、购买素材、源图和导出结果。
- 剪映 / CapCut 草稿、缓存、导出视频、账号信息、会员状态、客户素材和字幕原稿。
- `output/`、`scratch/`、临时文件、日志、报告产物和本机缓存。

## Windows 验证

```powershell
python -m unittest discover -s tests
python scripts\security_check.py
python scripts\collect_bridge_status.py --json
python examples\bridge_status.py --json
```

`examples\bridge_status.py` 在 CI 或未安装专业软件的机器上可能返回 `warn` / `missing`，这表示本机环境未配置，不表示仓库失败。真实软件探测和运行任务需要用户先安装、授权并手动确认对应桌面软件可用。

## 下一步

| 优先级 | 任务 |
| --- | --- |
| 高 | 稳定 ComfyUI txt2img、`img2img`、inpaint、upscale 和 workflow 校验 |
| 高 | 给 CAD 增加清楚的 JSON 参数格式、导出约定和 AutoCAD 本机测试说明 |
| 中 | 把 Photoshop 的 `document_info`、`extract_subject`、`export_png` 逐步封装成本机工具 |
| 中 | 给 Illustrator 增加只读文档信息、公开安全测试画板和 `trace_image_to_vector` 参数化示例 |
| 中 | 给 Blender 增加公开安全的基础场景生成脚本 |
| 中 | 给剪映 / CapCut 增加只读草稿目录探针，再验证最小测试草稿生成 |

协作原则：先把一条桥做真实、可运行、可测试，再扩展下一条桥。不要为了显得完整而把 research / planned 写成 stable。
