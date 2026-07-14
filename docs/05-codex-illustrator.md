# 5. Codex 接入 Illustrator / AI 矢量文件

## Related research package

- [Codex + Adobe AI integration map](adobe-ai-agent-integration-map.md)
- [Illustrator vector line rebuild pipeline](illustrator-vector-line-rebuild-pipeline.md)
- [Vector rebuild example scripts](../examples/illustrator_bridge/vector_rebuild/README.md)
- [Reference image vector reconstruction quality protocol](reference-image-vector-reconstruction.md)
- [Vector short-Chinese command language](vector-command-language.md)
- [Color-faithful vectorization protocol](color-faithful-vectorization.md)

这份文档说明 Adobe Illustrator 和 `.ai` 矢量文件桥的真实状态。这里的 **AI 文件** 指 Adobe Illustrator 的 `.ai` 矢量工程文件，不是“大模型 AI”。当前仓库有接入说明、`bridge.json` manifest、环境探测、sandbox demo，以及受控彩色 Image Trace 原型，状态是 `experimental local executor available`。Image Trace 已有默认 dry-run、固定 JSX、参数白名单和 sandbox 输出；没有用户授权参考图时只做静态与拒绝路径验证，不声称已完成视觉验收。

公开仓库只描述接入方式、参数化脚本方向和安全边界，不上传客户图稿、源图路径、导出结果或私有 `.ai` 工程。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| manifest | `examples/illustrator_bridge/bridge.json` | 声明状态、入口、支持任务和安全说明 |
| 环境探测 | `examples/illustrator_bridge/probe.ps1` | 检查 Illustrator 环境和 COM 线索 |
| 总状态探测 | `examples/bridge_status.py` | 检查 `ILLUSTRATOR_EXE` 和 `Illustrator.Application` COM |
| 当前文档信息 | `examples/illustrator_bridge/scripts/document_info.ps1` | 只读当前打开文档的名称、画板、图层和对象数量 |
| 只读 preflight | `examples/illustrator_bridge/scripts/preflight_plan.py` | 对脱敏文档摘要做链接、颜色模式、文本对象风险检查，不打开 `.ai` |
| sandbox 画板 demo | `examples/illustrator_bridge/scripts/create_demo_artboard.ps1` | 默认 dry-run；确认后创建公开安全测试 `.ai` |
| sandbox 导出 demo | `examples/illustrator_bridge/scripts/export_demo_assets.ps1` | 确认后只从 demo 文档导出 SVG、PNG 和 PDF |
| 彩色矢量化协议 | `protocols/color_vectorization.v1.schema.json` | 固定授权、彩色描摹参数、质量闸门和本地安全边界 |
| 彩色 Image Trace | `scripts/color_vectorize.ps1` + `jsx/color_vectorize.jsx` | 默认 dry-run；双确认后只处理明确传入的单张 PNG/JPEG，输出 AI/SVG/PNG 到 sandbox |
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
python examples\illustrator_bridge\scripts\preflight_plan.py --json
python -m unittest tests.test_color_vectorization
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\scripts\color_vectorize.ps1
```

## 推荐 MCP 工具方向

| 工具名 | 作用 | 当前状态 |
| --- | --- | --- |
| `illustrator.document_info` | 读取当前文档名称、画板数量、尺寸、颜色模式、图层和对象数量 | 已有只读脚本 |
| `illustrator.create_demo_artboard` | 创建公开安全测试画板和基础矢量对象 | 已有 sandbox demo，默认 dry-run |
| `illustrator.preflight` | 对脱敏文档摘要做只读 preflight，不打开 `.ai` | 已实现 metadata-only |
| `illustrator.color_vectorize_plan` | 生成 Photoshop / Illustrator 应用矩阵、彩色描摹参数和质量闸门 | 已实现，纯内存 dry-run |
| `illustrator.color_vectorize_validate` | 校验调用方提供的轮廓、色差、感知相似度和节点统计 | 已实现，不读取图片 |
| `illustrator.color_vectorize_execute` | 对明确传入的 PNG/JPEG 执行固定 Image Trace，输出 AI/SVG/PNG | 已实现受控本地原型，默认 dry-run、双确认 |
| `illustrator.export_demo_assets` | 从 sandbox demo 文档导出 SVG、PDF 和 PNG | 已有 sandbox demo，需显式确认 |
| `illustrator.run_demo` | 创建测试画板、导出 demo 产物并生成 manifest | 已有一键流程，需显式确认 |

旧规划名 `trace_image_to_vector` 已拆分为 plan / validate / execute 三个入口，避免把只读计划、质量验收和真实写入混在一个高风险工具里。

## 不能做什么

- 不能把 Image Trace 生成结果直接声称为“原样通过”；真实输出必须先看 PNG 预览并通过外部质量指标。
- 当前 Photoshop 预处理只进入应用矩阵计划，尚未提供真实执行器；不要写成已完成 PS + AI 全自动闭环。
- 不能提交 `.ai` 私有工程、客户图稿、商业字体、商业画笔、购买素材。
- 不能提交源图路径、微信临时路径、桌面路径、导出目录和真实项目输出。
- 不能提交 Illustrator 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能自动登录、绕过授权或批量抓取账号内云文档。

## 下一步

1. 保留 `examples/bridge_status.py` 的 Illustrator 状态检查入口。
2. 继续把 demo 输出保持在 `examples/output/illustrator/`，不提交真实生成物。
3. 补 Photoshop sandbox 预处理执行器，并保持源图只由参数传入。
4. 补参考图与 PNG 预览的本地像素比较器，再生成 VectorPatch 修复建议。
5. 扩展 preflight 检查，例如字体替换风险、颜色空间和链接资产风险。
6. 所有真实写入继续要求 dry-run 之后显式确认。
