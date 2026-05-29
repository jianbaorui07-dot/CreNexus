# 3. Codex 接入 Photoshop

这份文档说明 Photoshop 桥的真实状态。当前仓库已有诊断、COM 探针、当前文档信息读取、主体抠图实验、本机接入报告和 sandbox PSD/layer demo，状态是 `experimental demo available`。它还不是稳定的生产级修图自动化工作流。

公开仓库只保存通用协议、参数化脚本和安全边界，不保存 Photoshop 安装路径、账号、授权信息、PSD、素材路径、源图文件名或桌面输出路径。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 本机诊断 | `examples/photoshop_bridge/scripts/diagnose_local.ps1` | 检查安装线索、COM 注册、进程和可选 COM 探测 |
| 只读探针 | `examples/photoshop_bridge/probe.ps1` | 输出安全的 probe report |
| 当前文档信息 | `examples/photoshop_bridge/scripts/document_info.ps1` | 读取当前文档名称、尺寸、模式和图层数量 |
| sandbox PSD demo | `examples/photoshop_bridge/scripts/create_demo_document.ps1` | 默认 dry-run；确认后创建公开安全测试 PSD 和命名图层 |
| sandbox preview export | `examples/photoshop_bridge/scripts/export_demo_preview.ps1` | 确认后只从 demo PSD 导出 PNG / JPG preview |
| demo manifest | `examples/photoshop_bridge/write_demo_manifest.py` | 汇总本地 demo 输出，manifest 本身不提交 |
| COM 探针 | `examples/photoshop_bridge/scripts/com_probe.ps1` | 创建测试文档并导出 PNG |
| 主体抠图实验 | `examples/photoshop_bridge/scripts/extract_subject_to_png.ps1` | 输入和输出路径都由参数传入 |
| 本机接入报告 | `examples/photoshop_bridge/write_practice_report.py` | 汇总诊断、实操结果和 PNG 元数据 |
| 四联海报实验 | `examples/photoshop_bridge/experiments/4up_hex_poster/run_4up_hex_poster.ps1` | 生成参数化 JSX；本机完整执行会调用 Photoshop COM |

## 需要本机安装什么

- 已授权可用的 Adobe Photoshop desktop。
- Windows PowerShell。
- 可用的 `Photoshop.Application` COM。
- 如需 Python COM 探测，需要 pywin32。

真实路径只放本机环境变量或本地 `.env`：

```powershell
$env:PHOTOSHOP_EXE="<path-to-Photoshop.exe>"
```

运行前建议手动打开 Photoshop，避免脚本触发不受控启动流程。

## 验证命令

```powershell
npm.cmd run photoshop:diagnose
npm.cmd run photoshop:demo:plan
```

直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1 -ProbeCom
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

单独运行 COM 探针：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

主体抠图实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

生成本机接入报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```

报告会记录环境诊断、COM 探测、当前文档、一键实操和图片产物清单，包括 PNG 是否存在、文件大小、图片尺寸、透明像素统计、主体边界和 SHA256 摘要。

sandbox demo 命令：

```powershell
npm.cmd run photoshop:demo:plan
npm.cmd run photoshop:demo
npm.cmd run photoshop:manifest
```

真实输出只写入 `examples/output/photoshop/`，生成的 PSD、PNG、JPG 和 manifest JSON 不提交。

四联科技六边形海报实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1 -GenerateOnly
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1
```

该实验会本地生成分层 PSD、白底 PNG、透明 PNG 和预览 JPG。公开仓库只保留生成脚本、模板和 `sample_verification_report.json`，不保留实际输出图或本机路径。

## 不能做什么

- 不能提交 Photoshop 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能提交 PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- 不能提交源图路径、桌面路径或导出结果。
- 不能承诺复杂商业海报、复杂文字背景、线稿背景都能自动抠好。
- 不能把实验脚本说成稳定生产级工作流。
- 复杂商业修图、主体抠图和真实项目 PSD 仍然需要人工确认。

## 下一步

1. 稳定只读 `document_info`。
2. 把 `extract_subject` 和 `export_png` 封装成更小的参数化动作。
3. 增加二次蒙版、最大主体保留、边缘羽化和人工确认流程。
4. 评估 UXP 面板和本地 MCP 工具层。
5. 保持输入和输出路径都由参数传入，不写默认个人路径。
