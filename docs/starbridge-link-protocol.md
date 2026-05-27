# 星桥链接协议

这个文件是 **StarBridge / 星桥** 的公开入口页。旧链接仍然指向这里，所以这里不再只做跳转，而是直接说明：这个项目怎么读、本地软件桥怎么分工、Codex 如何通过 StarBridge 探针和 MCP stdio tools 接入本机创意软件，以及哪些内容不能进入 GitHub。

## 一、这个协议解决什么问题

星桥链接协议把 Codex 和本机创作软件连成一条可检查、可复用、可公开协作的工作链。现在这条链有两层：StarBridge 负责统一状态、探针和脱敏输出；MCP stdio server 负责把安全收敛后的能力暴露成 `tools/list` / `tools/call`。

| 角色 | 中文说明 |
| --- | --- |
| Codex | 写脚本、跑检查、整理说明、通过 MCP tools 调用本机桥 |
| GitHub | 只保存公开安全的文档、脚本、workflow、MCP server 和测试 |
| ComfyUI | 本地图像生成、修复、放大和 prompt 实验 |
| Blender | 本机三维场景、灯光、相机、材质和渲染 |
| CAD / AutoCAD | 工程制图、孔位、尺寸、图层和 DWG 输出 |
| Photoshop | 修图、主体选择、抠图、图层处理和 PNG 导出 |
| Illustrator | 矢量图形、线稿矢量化、SVG/PDF 导出 |
| 剪映 / CapCut | 短视频草稿、模板、字幕、时间线和导出确认 |

一句话：**StarBridge 管安全边界，MCP 管工具调用，专业软件管真实生产，私有资产只留本机。**

## 二、先看哪些文件

| 入口 | 中文用途 |
| --- | --- |
| `README.md` | 仓库总览、区域标注、快速检查命令 |
| `docs/中文介绍.md` | 星桥总协议，说明多条本地软件桥的完整路线 |
| `docs/中文用途索引.md` | 每个主要文件的中文用途索引 |
| `docs/local-mcp-setup.md` | 本地 MCP stdio server 配置和工具清单 |
| `docs/中文标注规范.md` | 区域命名、脚本输出和 CAD 图纸中文标注规则 |
| `docs/05-codex-illustrator.md` | Codex 接入 Illustrator / AI 矢量文件的中文说明 |
| `docs/06-codex-jianying.md` | Codex 接入剪映 / CapCut 的调研和本地草稿桥路线 |
| `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop、Illustrator 等本地桥 |

## 三、核心桥的区域划分

| 区域 | 目录或文件 | 当前能力 |
| --- | --- | --- |
| 图像生成桥 | `examples/comfy_bridge/` | MCP `comfyui.system_probe`、`comfyui.workflow_validate`，以及文生图 workflow |
| 三维场景桥 | `docs/04-codex-blender.md`、`examples/blender_bridge/` | MCP `blender.environment_probe` 和后续安全脚本方向 |
| 工程制图桥 | `cad-mcp-autocad/`、`examples/cad/`、`scripts/` | MCP `cad_autocad.environment_probe`、`autocad_dxf.*`、AutoCAD MCP 子项目 |
| Photoshop 修图桥 | `examples/photoshop_bridge/` | MCP `photoshop.session_info`、COM 探针、测试文档导出、主体抠图 |
| AI 矢量文件桥 | `docs/05-codex-illustrator.md`、`examples/illustrator_bridge/` | MCP `illustrator.document_info`、Illustrator `.ai` 路线和安全边界 |
| 剪映/CapCut 短视频剪辑桥 | `docs/06-codex-jianying.md`、`examples/capcut_jianying_bridge/` | MCP `jianying_capcut.draft_probe`、本地草稿桥调研和安全边界 |

### 3.1 AI 矢量文件桥怎么理解

中文创作场景里经常把 Adobe Illustrator 的 `.ai` 工程叫做 **AI 文件**。这里的 AI 矢量文件不是人工智能模型文件，而是可编辑的矢量设计文件。Codex 接入这条桥时，重点不是上传 `.ai` 私有工程，而是把可复用动作描述清楚：

| 输入 | Codex 做什么 | Illustrator 做什么 | 输出 |
| --- | --- | --- | --- |
| 线稿、黑白图、图标草图 | 生成参数、调用脚本、检查路径安全 | Image Trace、扩展路径、清理矢量 | SVG / PDF / PNG 预览 |
| 包装或物料尺寸 | 转成画板、参考线和图层参数 | 绘制路径、标注、导出校样 | `.ai` 本机工程和 PDF 校样 |
| 品牌图标草案 | 生成基础形状和文字占位 | 细化路径、颜色、版式和画板 | SVG / PDF / PNG |

公开仓库只保存接入说明、状态检查和通用脚本方向；客户图稿、私有 `.ai`、源图路径、导出结果和商业字体都只留本机。详细说明见 `docs/05-codex-illustrator.md`。

## 四、整体方案和本机实例对照

这里把 **项目整体** 和 **本机实例** 分开看：项目整体是 GitHub 里可公开协作的文档、脚本和路线；本机实例是当前电脑上真正安装、启动、授权和配置过的软件。缺的应用不写死到仓库里，而是用环境变量、手动启动和本机探针应用到本机。

| 软件桥 | 项目整体已有内容 | 本机实例检查项 | 本机没有时怎么补 |
| --- | --- | --- | --- |
| ComfyUI 图像生成桥 | `examples/comfy_bridge/`、文生图 workflow、API 探针 | `STARBRIDGE_COMFYUI_URL`、`COMFY_ROOT`、`COMFY_LAUNCHER`，以及 `127.0.0.1:8188` 是否可连接 | 先启动 ComfyUI；如目录不在默认位置，用环境变量配置，不提交模型和输出图 |
| Blender 三维场景桥 | `docs/04-codex-blender.md` 和后续场景脚本路线 | `BLENDER_EXE`、`BLENDER_MCP_DIR` | 安装或打开 Blender；配置本机路径环境变量，不提交 `.blend`、贴图和资产库 |
| CAD / AutoCAD 工程制图桥 | `cad-mcp-autocad/`、`AUTOCAD_MCP_SETUP.md`、`scripts/` | `AUTOCAD_EXE`、`pywin32/win32com`、AutoCAD MCP 子项目 | 安装/打开 AutoCAD；配置 `AUTOCAD_EXE`；客户 DWG 和真实图纸只留本机 |
| Photoshop 修图桥 | `examples/photoshop_bridge/`、诊断、COM 探针、主体抠图实验 | `PHOTOSHOP_EXE`、`Photoshop.Application` COM、运行中的 Photoshop | 手动打开已授权 Photoshop；需要时配置 `PHOTOSHOP_EXE`；输入/输出路径只用参数传入 |
| AI 矢量文件桥 | `docs/05-codex-illustrator.md`、Illustrator / `.ai` 接入路线 | `ILLUSTRATOR_EXE`、`Illustrator.Application` COM、运行中的 Illustrator | 手动打开已授权 Illustrator；配置 `ILLUSTRATOR_EXE`；客户 `.ai`、源图和导出结果不提交 |
| 剪映/CapCut 草稿桥 | `docs/06-codex-jianying.md`、本地草稿桥调研 | `JIANYING_EXE`、`CAPCUT_EXE`、`JIANYING_DRAFTS_DIR`、`CAPCUT_DRAFTS_DIR` | 用户手动确认软件和草稿目录；用环境变量提供目录；草稿、素材和导出视频不进 Git |

本机实例统一用这个命令查看：

```powershell
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
```

如果某条桥显示 `未找到` 或 `需配置`，优先按上表在本机补环境变量或手动打开软件。不要把真实安装路径、草稿目录、素材目录、源图路径或导出目录写进公开文档。

## 五、Photoshop 本机接入实操

这条桥已经可以在 Windows 本机通过 `Photoshop.Application` COM 对象执行 Photoshop JavaScript。

### 5.1 前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows |
| Photoshop | 已安装、已授权、可以正常打开 |
| COM 注册 | `Photoshop.Application` 能被 PowerShell 创建 |
| 本机路径 | 不写进 Git，用参数或环境变量传入 |

可以先检查当前已接入桥状态：

```powershell
python examples\bridge_status.py
```

### 5.2 先做环境诊断

只检查 Photoshop 安装线索、COM 注册、进程状态，不强制跑图像处理：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
```

连 COM 一起验证：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1 -ProbeCom
```

诊断结果里的关键字段：

| 字段 | 中文说明 |
| --- | --- |
| `status` | 当前状态：`ready`、`com_registered` 或 `needs_configuration` |
| `com_registered` | 是否注册了 `Photoshop.Application` |
| `running_processes` | 当前是否已有 Photoshop 进程 |
| `discovered_paths` | 在常见 Adobe 目录里找到的 Photoshop.exe |
| `com_probe` | 加 `-ProbeCom` 时返回版本和当前文档数量 |
| `next_step` | 下一步建议 |

### 5.3 一键实操命令

运行下面命令，会自动完成三件事：

1. 连接 Photoshop 并创建测试文档。
2. 生成一张公开安全的本地测试图。
3. 调用 Photoshop 主体选择，导出透明 PNG。

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
```

默认输出目录：

```text
output\photoshop_bridge_practice\
```

这个目录属于本机生成物，已经被 `.gitignore` 的 `output/` 规则排除，不会提交到 GitHub。

### 5.4 读取当前文档信息

如果 Photoshop 已经打开，可以读取当前文档名称、尺寸、模式和图层数量：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

这个命令不保存图片，只读取当前 Photoshop 状态。

### 5.5 生成本机接入报告

生成中文 Markdown 和 JSON 报告，汇总环境诊断、COM 探测、当前文档信息：

```powershell
python examples\photoshop_bridge\write_practice_report.py
```

如果要把一键实操结果也写进报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```

默认输出目录：

```text
output\photoshop_bridge_report\
```

报告文件：

| 文件 | 中文说明 |
| --- | --- |
| `photoshop_bridge_report.md` | 给人看的中文报告 |
| `photoshop_bridge_report.json` | 给脚本读取的结构化结果 |
| `practice\` | 加 `--run-practice` 时保存探针图、测试图和抠图结果 |

报告会汇总：

| 报告区域 | 中文说明 |
| --- | --- |
| 环境诊断 | COM 注册、CLSID、`PHOTOSHOP_EXE`、下一步建议 |
| COM 探测 | Photoshop 版本和当前文档数量 |
| 当前文档 | 活动文档名称、尺寸、模式、图层数量 |
| 一键实操 | 探针图、测试图、抠图方法和抠图输出 |
| 产物清单 | PNG 是否存在、文件大小、图片尺寸、透明像素统计、主体边界、SHA256 摘要 |

一键实操开始时会清理本轮固定产物文件，避免旧图误入报告。如果 Photoshop 临时忙碌，实操脚本会短暂等待并重试；如果仍然失败，报告仍会按固定输出目录回收本轮已经生成的探针图、测试图和抠图 PNG。

### 5.6 验收标准

一次 Photoshop 本机接入视为“跑通”，至少满足：

| 检查项 | 合格标准 |
| --- | --- |
| 环境诊断 | `diagnose_local.ps1 -ProbeCom` 返回 `status: ready` |
| 当前文档 | `document_info.ps1` 能返回 Photoshop 版本和文档数量 |
| 一键实操 | `run_local_practice.ps1` 返回 `ok: true` |
| 报告留档 | `write_practice_report.py --run-practice` 生成 Markdown 和 JSON |
| 图片产物 | 产物清单中探针图、测试图、抠图 PNG 都存在且有 PNG 尺寸 |
| 透明 PNG | 主体抠图 PNG 有透明通道，并显示透明/半透明/不透明像素统计 |
| 主体边界 | 主体抠图 PNG 显示 alpha 主体边界、四边边距和主体像素占比 |
| Git 安全 | `output/` 中的图片和报告不进入 Git 提交 |

### 5.7 单独运行 COM 探针

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

成功时会返回 JSON，包含 Photoshop 版本、测试文档名称、图层数量和 PNG 输出路径。

### 5.8 单独运行主体抠图

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

脚本会调用 Photoshop 的主体选择能力，输出透明 PNG。复杂背景、海报文字、线稿背景可能需要人工二次修边。

## 六、Photoshop 桥文件标注

| 文件 | 中文用途 |
| --- | --- |
| `examples/photoshop_bridge/README.md` | Photoshop 本地桥中文说明 |
| `examples/photoshop_bridge/write_practice_report.py` | 生成本机接入 Markdown / JSON 报告 |
| `examples/photoshop_bridge/scripts/diagnose_local.ps1` | 本机诊断：安装线索、COM 注册、进程和可选 COM 探测 |
| `examples/photoshop_bridge/scripts/document_info.ps1` | 当前文档信息：名称、尺寸、模式、图层数量 |
| `examples/photoshop_bridge/scripts/run_local_practice.ps1` | 一键本机实操：探针、测试图、主体抠图 |
| `examples/photoshop_bridge/scripts/com_probe.ps1` | COM 探针：创建测试文档并导出 PNG |
| `examples/photoshop_bridge/scripts/extract_subject_to_png.ps1` | 主体选择：输入图片，输出透明 PNG |
| `docs/photoshop-codex-bridge.md` | Photoshop 本地桥详细方案和后续 MCP 方向 |
| `docs/03-codex-photoshop.md` | Codex 接入 Photoshop 的单项中文文档 |

## 七、输出结果怎么处理

| 输出类型 | 建议位置 | 是否提交 |
| --- | --- | --- |
| Photoshop 接入报告 | `output\photoshop_bridge_report\` | 不提交 |
| Photoshop 探针 PNG | `output\photoshop_bridge_practice\` | 不提交 |
| 主体抠图 PNG | `output\photoshop_bridge_practice\` | 不提交 |
| 临时测试图 | `output\photoshop_bridge_practice\` | 不提交 |
| AI 私有工程 | 本机私有目录 | 不提交 |
| SVG/PDF/PNG 导出结果 | 本机临时目录或 `output\` | 不提交 |
| 脚本和说明 | `examples/`、`docs/` | 可以提交 |
| 私有 PSD、客户图、商业素材 | 本机私有目录 | 不提交 |

## 八、安全边界

允许进入 GitHub：

- 协议文档、README、中文索引。
- 通用 PowerShell / Python 示例脚本。
- 不含账号、不含私有素材、不含真实路径的示例 workflow。
- 本地实操脚本本身。

禁止进入 GitHub：

- Photoshop 安装路径、Creative Cloud 缓存、账号、许可证、Cookie、token。
- PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- Illustrator `.ai` 私有工程、商业字体、商业画笔、购买素材、客户图稿和导出结果。
- 源图、导出图、抠图结果、桌面路径、真实项目输出。
- 剪映 / CapCut 草稿、缓存、导出视频、字幕原稿、会员状态和账号信息。
- 任何需要登录、订阅、验证码、OAuth 或人工授权的信息。

## 九、故障排查表

| 现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| `needs_configuration` | 未安装 Photoshop，或 COM 没注册 | 安装并打开一次 Photoshop，再运行 `diagnose_local.ps1 -ProbeCom` |
| `com_registered` 但不是 `ready` | COM 注册存在，但还没实际创建对象 | 运行 `diagnose_local.ps1 -ProbeCom`，观察 `com_probe.error` |
| `New-Object -ComObject` 报错 | Photoshop 授权、安装或 COM 注册异常 | 手动打开 Photoshop，确认能正常进入主界面 |
| `document_info.ps1` 没有活动文档 | Photoshop 已打开但没有文档 | 先打开或创建一个文档，再运行脚本 |
| 主体抠图带出背景 | 背景复杂、文字干扰、主体边界不清 | 换干净输入图，或人工二次修边、羽化蒙版 |
| 报告生成失败 | PowerShell 子脚本失败或 JSON 输出异常 | 先单独运行诊断脚本，确认哪个环节失败 |
| 产物清单缺尺寸 | 输出不是 PNG，或文件未生成完整 | 重新运行 `write_practice_report.py --run-practice`，检查 `practice\` 目录 |
| 实操失败但有图片 | Photoshop 忙碌或中途异常，部分图片已经写出 | 报告会按固定文件名回收已生成产物；等待 Photoshop 空闲后再运行一次 |
| 抠图 PNG 无透明通道 | Photoshop 没有正确隐藏背景或保存透明层 | 重新运行主体抠图，确认输出为 PNG 且背景图层不可见 |
| 透明像素为 0 | 主体选择没有产生透明背景，或整张图被视为主体 | 换更干净的输入图，或人工建立选区后再导出 |
| 主体边界贴边 | 主体被裁掉，或输入图主体超出画面 | 换留白更充足的输入图，或先扩展画布再运行主体选择 |

## 十、后续优化路线

| 优先级 | 任务 |
| --- | --- |
| 已完成 | 生成 Photoshop 本机接入 Markdown / JSON 报告 |
| 已完成 | 让 `write_practice_report.py` 汇总图片大小、尺寸和哈希摘要 |
| 已完成 | 增加 Photoshop 输出透明通道检查和 alpha 像素统计 |
| 已完成 | 增加主体边界盒质量指标 |
| 已完成 | 增加 Photoshop 当前文档信息读取脚本 |
| 已完成 | 增加 Photoshop 本机环境诊断脚本 |
| 已完成 | 增加 AI 矢量文件桥中文说明入口 |
| 中 | 把 `extract_subject`、`export_png` 封装成本机 MCP 工具 |
| 中 | 给 Illustrator 增加只读文档信息、测试画板和 Image Trace 参数化示例 |
| 中 | 增加二次蒙版、边缘羽化和人工确认流程 |
| 低 | 评估 UXP 面板，把当前文档、图层、选择区暴露给本地桥 |

## 十一、最短执行路径

如果只想确认本机 Photoshop 实验桥是否跑通，执行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
```

看到 `ok: true`，并且输出目录里出现探针 PNG 和主体抠图 PNG，只能说明本机 Photoshop 实验桥跑通；它还不是生产级完整自动化工作流。

如果想留下可读记录，执行：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```
