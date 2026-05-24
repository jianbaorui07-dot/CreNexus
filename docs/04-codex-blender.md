# 4. Codex 接入 Blender

这份文档说明 Blender 桥的真实状态。当前仓库有 Blender 接入说明、`bridge.json` manifest 和环境探针，状态是 `planned`。公开安全的场景生成、渲染闭环和 Blender MCP 示例还没有完成。

公开仓库只保存通用说明、状态检查和后续脚本入口，不保存私有 `.blend`、贴图、资产库、渲染缓存或本机路径。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| manifest | `examples/blender_bridge/bridge.json` | 声明状态、入口、支持任务和安全说明 |
| 环境探针 | `examples/blender_bridge/probe.py` | 检查 Blender 可执行文件、本机配置和公开安全 report |
| 总状态探测 | `examples/bridge_status.py` | 检查 `BLENDER_EXE`、常见安装路径和 `BLENDER_MCP_DIR` |

## 需要本机安装什么

- Blender desktop 或 blender CLI。
- Python 3.10+。
- 如果使用 MCP 方向，需要本机 Blender MCP 项目目录。

真实路径只放本机环境变量：

```powershell
$env:BLENDER_EXE="<path-to-blender.exe>"
$env:BLENDER_MCP_DIR="<path-to-blender-mcp>"
```

## 验证命令

```powershell
npm.cmd run status:probe:json
```

直接运行：

```powershell
python examples\blender_bridge\probe.py
python examples\bridge_status.py --probe-executables --json
```

状态脚本会优先读取 `BLENDER_EXE` 和 `BLENDER_MCP_DIR`，也会检查常见安装路径。不要把个人路径写进公开文档。

## 不能做什么

- 当前没有发布 Blender 生成脚本，不能声称已经能自动建模或渲染。
- 不能提交私有 `.blend`、贴图、HDRI、资产库、渲染缓存。
- 不能提交商业模型、购买素材或客户场景。
- 不能让 CI 依赖真实安装 Blender。

## 下一步

1. 增加 `examples/blender_bridge/create_scene.py`，只使用程序生成的几何体、材质、灯光和相机。
2. 增加 `render_probe.py`，验证 Blender 可执行文件、渲染器和输出目录。
3. 只把渲染输出放在本机 `output/` 或临时目录，不提交图片。
4. 评估 Blender MCP 项目结构，再决定是否纳入本仓库。
