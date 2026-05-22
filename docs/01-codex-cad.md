# 1. Codex 接入 CAD

这份文档说明 Codex 如何接入 CAD / AutoCAD 类工程制图软件。公开仓库只保存通用脚本、协议和示例，不保存个人安装路径、客户图纸、DWG 成品或授权信息。

## 接入目标

- 让 Codex 根据结构化参数生成工程图草稿。
- 通过 AutoCAD COM 或 CAD MCP 调用本地 CAD 软件。
- 把点、线、圆、孔位、图层、标注等制图动作变成可复用脚本。
- 让生成结果留在本机 `output/`，不进入 GitHub。

## 当前入口

| 文件或目录 | 用途 |
| --- | --- |
| `cad-mcp-autocad/` | AutoCAD MCP 子项目 |
| `AUTOCAD_MCP_SETUP.md` | AutoCAD MCP 通用配置说明 |
| `scripts/test_autocad_mcp.py` | MCP 连接测试脚本 |
| `scripts/draw_connection_plate_from_spec.py` | 参数化连接板示例 |
| `scripts/draw_reference_mechanical_part.py` | 参考机械零件绘图示例 |

## 本地配置

不要把真实安装路径写进仓库。每台机器用环境变量配置：

```powershell
$env:AUTOCAD_EXE="<path-to-acad.exe>"
```

安装 Python 依赖：

```powershell
python -m pip install --user pywin32 mcp pydantic
```

## 验证命令

```powershell
python examples\bridge_status.py --json
python scripts\test_autocad_mcp.py
```

如果 AutoCAD 已打开，脚本会尝试通过本地 COM / MCP 调用绘图动作。生成的 DWG 只保留本机，不提交。

## 安全边界

- 不提交客户 DWG、商业图纸、授权文件、真实项目输出。
- 不把 AutoCAD 安装路径、用户目录、Codex 本地配置路径写进公开文档。
- 示例图纸只能使用虚构参数和公开安全几何。
- 所有批量导出默认输出到本机生成目录。

## 后续优化

- 增加更清楚的 JSON 参数格式。
- 把常用绘图动作封装成 MCP 工具。
- 增加标准零件库示例，但不带任何客户图纸。
- 让 `bridge_status.py` 更清楚地区分：未安装、未启动、COM 不可用、MCP 可用。
