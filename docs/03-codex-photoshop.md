# 3. Codex 接入 Photoshop

这份文档说明 Codex 如何接入 Photoshop。公开仓库只保存通用协议、脚本和安全边界，不保存 Photoshop 安装路径、账号、授权信息、PSD、素材路径、源图文件名或桌面输出路径。

## 接入目标

- 让 Codex 连接已授权可用的本地 Photoshop。
- 通过 Windows COM + Photoshop JavaScript 做最小自动化。
- 支持创建测试文档、读取版本、导出 PNG、调用主体选择和透明 PNG 输出。
- 后续升级到 UXP 面板和 MCP 工具层。

## 当前入口

| 文件或目录 | 用途 |
| --- | --- |
| `docs/photoshop-codex-bridge.md` | Photoshop 本地桥详细方案 |
| `examples/photoshop_bridge/README.md` | Photoshop 示例说明 |
| `examples/photoshop_bridge/write_practice_report.py` | 生成本机接入 Markdown / JSON 报告 |
| `examples/photoshop_bridge/scripts/diagnose_local.ps1` | 本机诊断：安装线索、COM 注册、进程和可选 COM 探测 |
| `examples/photoshop_bridge/scripts/document_info.ps1` | 当前文档信息：名称、尺寸、模式、图层数量 |
| `examples/photoshop_bridge/scripts/run_local_practice.ps1` | 一键本机实操：COM 探针、测试图生成、主体抠图 |
| `examples/photoshop_bridge/scripts/com_probe.ps1` | COM 探针，创建测试文档并导出 PNG |
| `examples/photoshop_bridge/scripts/extract_subject_to_png.ps1` | 主体选择和透明 PNG 输出实验 |

## 本地配置

真实路径只放本机环境变量或本地 `.env`：

```powershell
$env:PHOTOSHOP_EXE="<path-to-Photoshop.exe>"
```

运行前建议手动打开 Photoshop，避免脚本触发不受控启动流程。

## 验证命令

本机诊断：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1 -ProbeCom
```

一键本机实操：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
```

读取当前文档信息：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

生成本机接入报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```

报告会包含环境诊断、COM 探测、当前文档、一键实操和图片产物清单。产物清单会记录 PNG 是否存在、文件大小、图片尺寸、透明像素统计、主体边界和 SHA256 摘要。

一键实操会先清理本轮固定产物文件，避免旧图误入报告。遇到 Photoshop 忙碌时会短暂重试；即使仍然失败，报告也会按固定文件名回收本轮已生成的本地产物。

单独运行 COM 探针：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

主体抠图实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

复杂海报、文字背景、线稿背景会影响主体选择质量。脚本适合作为半自动起点，商业级精修仍需要人工修边或更强的蒙版流程。

## 安全边界

- 不提交 Photoshop 安装路径、Creative Cloud 缓存、账号、许可证、Cookie、token。
- 不提交 PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- 不提交源图路径、桌面路径、输出结果。
- 所有会修改图像的脚本默认输出新文件，不覆盖原图。

## 后续优化

- 增加 UXP 面板，读取当前文档名称、尺寸、图层数量。
- 增加本地 `127.0.0.1` 桥，让 Photoshop 状态可被 Codex 读取。
- 把稳定动作封装成 MCP：`get_document_info`、`extract_subject`、`export_png`。
- 增加二次蒙版、最大主体保留、边缘羽化和人工确认流程。
