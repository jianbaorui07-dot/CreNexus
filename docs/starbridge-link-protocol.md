# 星桥链接协议

这个文件是 **StarBridge / 星桥** 的公开入口页。旧链接仍然指向这里，所以这里不再只做跳转，而是直接说明：这个项目怎么读、四条本地软件桥怎么分工、Codex 如何在本机接入 Photoshop，以及哪些内容不能进入 GitHub。

## 一、这个协议解决什么问题

星桥链接协议把 Codex 和本机创作软件连成一条可检查、可复用、可公开协作的工作链：

| 角色 | 中文说明 |
| --- | --- |
| Codex | 写脚本、跑检查、整理说明、调用本机软件 |
| GitHub | 只保存公开安全的文档、脚本、workflow 和测试 |
| ComfyUI | 本地图像生成、修复、放大和 prompt 实验 |
| Blender | 本机三维场景、灯光、相机、材质和渲染 |
| CAD / AutoCAD | 工程制图、孔位、尺寸、图层和 DWG 输出 |
| Photoshop | 修图、主体选择、抠图、图层处理和 PNG 导出 |

一句话：**Codex 负责连接和自动化，专业软件负责生成和处理，私有资产只留本机。**

## 二、先看哪些文件

| 入口 | 中文用途 |
| --- | --- |
| `README.md` | 仓库总览、区域标注、快速检查命令 |
| `docs/中文介绍.md` | 星桥总协议，说明四条桥的完整路线 |
| `docs/中文用途索引.md` | 每个主要文件的中文用途索引 |
| `docs/中文标注规范.md` | 区域命名、脚本输出和 CAD 图纸中文标注规则 |
| `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop 四条桥 |

## 三、四条桥的区域划分

| 区域 | 目录或文件 | 当前能力 |
| --- | --- | --- |
| 图像生成桥 | `examples/comfy_bridge/` | 检查 ComfyUI、列出 checkpoint、提交文生图 workflow |
| 三维场景桥 | `docs/04-codex-blender.md` | 记录 Blender 接入方式和后续脚本方向 |
| 工程制图桥 | `cad-mcp-autocad/`、`scripts/` | AutoCAD MCP、COM 绘图、中文区域标注示例图 |
| Photoshop 修图桥 | `examples/photoshop_bridge/` | COM 探针、测试文档导出、主体抠图、一键本机实操 |

## 四、Photoshop 本机接入实操

这条桥已经可以在 Windows 本机通过 `Photoshop.Application` COM 对象执行 Photoshop JavaScript。

### 4.1 前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows |
| Photoshop | 已安装、已授权、可以正常打开 |
| COM 注册 | `Photoshop.Application` 能被 PowerShell 创建 |
| 本机路径 | 不写进 Git，用参数或环境变量传入 |

可以先检查四条桥状态：

```powershell
python examples\bridge_status.py
```

### 4.2 先做环境诊断

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

### 4.3 一键实操命令

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

### 4.4 读取当前文档信息

如果 Photoshop 已经打开，可以读取当前文档名称、尺寸、模式和图层数量：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

这个命令不保存图片，只读取当前 Photoshop 状态。

### 4.5 生成本机接入报告

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

### 4.6 验收标准

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

### 4.7 单独运行 COM 探针

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

成功时会返回 JSON，包含 Photoshop 版本、测试文档名称、图层数量和 PNG 输出路径。

### 4.8 单独运行主体抠图

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

脚本会调用 Photoshop 的主体选择能力，输出透明 PNG。复杂背景、海报文字、线稿背景可能需要人工二次修边。

## 五、Photoshop 桥文件标注

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

## 六、输出结果怎么处理

| 输出类型 | 建议位置 | 是否提交 |
| --- | --- | --- |
| Photoshop 接入报告 | `output\photoshop_bridge_report\` | 不提交 |
| Photoshop 探针 PNG | `output\photoshop_bridge_practice\` | 不提交 |
| 主体抠图 PNG | `output\photoshop_bridge_practice\` | 不提交 |
| 临时测试图 | `output\photoshop_bridge_practice\` | 不提交 |
| 脚本和说明 | `examples/`、`docs/` | 可以提交 |
| 私有 PSD、客户图、商业素材 | 本机私有目录 | 不提交 |

## 七、安全边界

允许进入 GitHub：

- 协议文档、README、中文索引。
- 通用 PowerShell / Python 示例脚本。
- 不含账号、不含私有素材、不含真实路径的示例 workflow。
- 本地实操脚本本身。

禁止进入 GitHub：

- Photoshop 安装路径、Creative Cloud 缓存、账号、许可证、Cookie、token。
- PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- 源图、导出图、抠图结果、桌面路径、真实项目输出。
- 任何需要登录、订阅、验证码、OAuth 或人工授权的信息。

## 八、故障排查表

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

## 九、后续优化路线

| 优先级 | 任务 |
| --- | --- |
| 已完成 | 生成 Photoshop 本机接入 Markdown / JSON 报告 |
| 已完成 | 让 `write_practice_report.py` 汇总图片大小、尺寸和哈希摘要 |
| 已完成 | 增加 Photoshop 输出透明通道检查和 alpha 像素统计 |
| 已完成 | 增加主体边界盒质量指标 |
| 已完成 | 增加 Photoshop 当前文档信息读取脚本 |
| 已完成 | 增加 Photoshop 本机环境诊断脚本 |
| 中 | 把 `extract_subject`、`export_png` 封装成本机 MCP 工具 |
| 中 | 增加二次蒙版、边缘羽化和人工确认流程 |
| 低 | 评估 UXP 面板，把当前文档、图层、选择区暴露给本地桥 |

## 十、最短执行路径

如果只想确认 Codex 已经能接入本机 Photoshop，执行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
```

看到 `ok: true`，并且输出目录里出现探针 PNG 和主体抠图 PNG，就说明本机 Photoshop 桥已经跑通。

如果想留下可读记录，执行：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```
