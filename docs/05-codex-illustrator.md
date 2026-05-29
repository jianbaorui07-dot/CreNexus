# 5. Codex 接入 Illustrator / AI 矢量文件

这份文档说明 Adobe Illustrator 和 `.ai` 矢量文件桥的真实状态。这里的 **AI 文件** 指 Adobe Illustrator 的 `.ai` 矢量工程文件，不是“大模型 AI”。当前仓库有接入说明、`bridge.json` manifest、环境探测和 sandbox demo，状态是 `experimental demo available`。已补齐当前文档信息读取、测试画板创建，以及 SVG/PDF/PNG demo 导出；Image Trace 仍是下一阶段能力。

公开仓库只描述接入方式、参数化脚本方向和安全边界，不上传客户图稿、源图路径、导出结果或私有 `.ai` 工程。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| manifest | `examples/illustrator_bridge/bridge.json` | 声明状态、入口、支持任务和安全说明 |
| 环境探测 | `examples/illustrator_bridge/probe.ps1` | 检查 Illustrator 环境和 COM 线索 |
| 总状态探测 | `examples/bridge_status.py` | 检查 `ILLUSTRATOR_EXE` 和 `Illustrator.Application` COM |
| 当前文档信息 | `examples/illustrator_bridge/scripts/document_info.ps1` | 只读当前打开文档的名称、画板、图层和对象数量 |
| sandbox 画板 demo | `examples/illustrator_bridge/scripts/create_demo_artboard.ps1` | 默认 dry-run；确认后创建公开安全测试 `.ai` |
| sandbox 导出 demo | `examples/illustrator_bridge/scripts/export_demo_assets.ps1` | 确认后只从 demo 文档导出 SVG、PNG 和 PDF |
| demo manifest | `examples/illustrator_bridge/write_demo_manifest.py` | 汇总本地 demo 输出，manifest 本身不提交 |

## 需要本机安装什么

- 已授权可用的 Adobe Illustrator desktop。
- Windows PowerShell。
- 可用的 `Illustrator.Application` COM。
- 如需 Python COM 探测，需要 pywin32。

真实路径只放本机环境变量：

```powershell
$env:ILLUSTRATOR_EXE="<path-to-Illustrator.exe>"
```

## 验证命令

```powershell
npm.cmd run status:probe:json
```

直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\probe.ps1
python examples\bridge_status.py --probe-executables --json
```

## 推荐 MCP 工具方向

| 工具名 | 作用 | 当前状态 |
| --- | --- | --- |
| `illustrator.document_info` | 读取当前文档名称、画板数量、尺寸、颜色模式、图层和对象数量 | 已有只读脚本 |
| `illustrator.create_demo_artboard` | 创建公开安全测试画板和基础矢量对象 | 已有 sandbox demo，默认 dry-run |
| `trace_image_to_vector` | 输入图片，调用 Image Trace，导出 SVG/PDF | 待补脚本 |
| `illustrator.export_demo_assets` | 从 sandbox demo 文档导出 SVG、PDF 和 PNG | 已有 sandbox demo，需显式确认 |
| `illustrator.run_demo` | 创建测试画板、导出 demo 产物并生成 manifest | 已有一键流程，需显式确认 |

## 不能做什么

- 当前不能声称已经完成 Image Trace；SVG/PDF/PNG 只限 sandbox demo 导出。
- 不能提交 `.ai` 私有工程、客户图稿、商业字体、商业画笔、购买素材。
- 不能提交源图路径、微信临时路径、桌面路径、导出目录和真实项目输出。
- 不能提交 Illustrator 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能自动登录、绕过授权或批量抓取账号内云文档。

## 下一步

1. 保留 `examples/bridge_status.py` 的 Illustrator 状态检查入口。
2. 继续把 demo 输出保持在 `examples/output/illustrator/`，不提交真实生成物。
3. 再做 `trace_image_to_vector`，输入和输出路径全部参数化。
4. 稳定后补更多 preflight 检查，例如字体、颜色空间和链接资产风险。
5. 所有真实写入继续要求 dry-run 之后显式确认。
