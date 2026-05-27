# 5. Codex 接入 Illustrator / AI 矢量文件

这份文档说明 Adobe Illustrator 和 `.ai` 矢量文件桥的真实状态。这里的 **AI 文件** 指 Adobe Illustrator 的 `.ai` 矢量工程文件，不是“大模型 AI”。当前仓库有接入说明、`bridge.json` manifest 和环境探测，状态是 `planned`。Image Trace、SVG/PDF/PNG 标准化导出还没有公开脚本。

公开仓库只描述接入方式、参数化脚本方向和安全边界，不上传客户图稿、源图路径、导出结果或私有 `.ai` 工程。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| manifest | `examples/illustrator_bridge/bridge.json` | 声明状态、入口、支持任务和安全说明 |
| 环境探测 | `examples/illustrator_bridge/probe.ps1` | 检查 Illustrator 环境和 COM 线索 |
| 总状态探测 | `examples/bridge_status.py` | 检查 `ILLUSTRATOR_EXE` 和 `Illustrator.Application` COM |

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
| `get_document_info` | 读取当前文档名称、画板数量、尺寸和颜色模式 | 待补脚本 |
| `create_test_artboard` | 创建公开安全测试画板和基础矢量对象 | 待补脚本 |
| `trace_image_to_vector` | 输入图片，调用 Image Trace，导出 SVG/PDF | 待补脚本 |
| `export_svg` | 导出当前文档或指定画板为 SVG | 待补脚本 |
| `export_pdf` | 导出 PDF 校样 | 待补脚本 |
| `export_png` | 导出预览 PNG | 待补脚本 |

## 不能做什么

- 当前不能声称已经完成 Image Trace、SVG/PDF/PNG 标准化导出。
- 不能提交 `.ai` 私有工程、客户图稿、商业字体、商业画笔、购买素材。
- 不能提交源图路径、微信临时路径、桌面路径、导出目录和真实项目输出。
- 不能提交 Illustrator 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能自动登录、绕过授权或批量抓取账号内云文档。

## 下一步

1. 保留 `examples/bridge_status.py` 的 Illustrator 状态检查入口。
2. 新增只读当前文档信息脚本，先读取文档和画板状态，不导出文件。
3. 新增公开安全的测试画板脚本，只绘制基础矢量对象。
4. 再做 `trace_image_to_vector`，输入和输出路径全部参数化。
5. 稳定后封装成本机 MCP 工具，让 Codex 能调用、记录结果并提示风险。
