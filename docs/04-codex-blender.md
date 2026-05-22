# 4. Codex 接入 Blender

这份文档说明 Codex 如何接入 Blender。公开仓库只保存通用说明、状态检查和公开安全示例，不保存私有 `.blend`、贴图、资产库、渲染缓存或本机路径。

## 接入目标

- 让 Codex 通过 Blender Python 或 Blender MCP 调用本地 Blender。
- 自动创建基础场景、几何体、材质、灯光、相机和渲染参数。
- 把文字需求或概念图转成可修改的三维初稿。
- 后续把稳定动作封装成 MCP 工具。

## 当前入口

| 文件或目录 | 用途 |
| --- | --- |
| `examples/bridge_status.py` | 检查 Blender 可执行文件和 MCP 桥配置 |
| `docs/starbridge-link-protocol.md` | StarBridge 总协议 |
| `docs/codex-drawing-tool-integrations.md` | 绘画和创作工具接入路线 |

当前仓库还没有发布 Blender 生成脚本。下一步应新增公开安全的示例脚本，例如基础展台、产品方块、灯光相机和渲染输出。

## 本地配置

真实路径只放本机环境变量：

```powershell
$env:BLENDER_EXE="<path-to-blender.exe>"
$env:BLENDER_MCP_DIR="<path-to-blender-mcp>"
```

## 验证命令

```powershell
python examples\bridge_status.py --probe-executables
```

状态脚本会优先读取 `BLENDER_EXE` 和 `BLENDER_MCP_DIR`，也会检查常见安装路径。不要把个人路径写进公开文档。

## 安全边界

- 不提交私有 `.blend`、贴图、HDRI、资产库、渲染缓存。
- 不提交商业模型、购买素材、客户场景。
- 示例脚本只使用程序生成的几何体、材质和灯光。
- 输出渲染图只留本机，不进入 GitHub。

## 后续优化

- 新增 `examples/blender_bridge/`。
- 增加 `create_scene.py`：生成公开安全基础场景。
- 增加 `render_probe.py`：验证 Blender 可执行文件、渲染器和输出目录。
- 评估 Blender MCP 项目结构，再决定是否纳入本仓库。
