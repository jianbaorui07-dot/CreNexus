# StarBridge Canvas 实时画布

StarBridge Canvas 把 `codexhuabu` 的本地无限画布迁入 StarBridge 项目，用作 Codex 和创意软件之间的可视化协作层。它不是素材仓库；真实项目画布、截图、生成图和页面资产默认保存在本机忽略目录。

## 运行

```powershell
npm.cmd run canvas:dev -- -ProjectDir "C:\path\to\project"
```

默认地址：

```text
http://127.0.0.1:43217
```

如果需要换端口：

```powershell
npm.cmd run canvas:dev -- -ProjectDir "C:\path\to\project" -Port 43218
```

## 实时机制

StarBridge Canvas 使用三条本地接口：

| 接口 | 用途 |
| --- | --- |
| `/api/canvas` | 读取和保存完整 tldraw 快照 |
| `/api/canvas-events` | Server-Sent Events 实时广播 |
| `/api/canvas-live` | 接收轻量绘制事件，例如新增、更新、删除对象 |

绘制时，浏览器会先把轻量变化广播给其他打开的画布窗口，再通过快照保存让其他窗口刷新完整画布。这个设计把“绘制过程实时可见”和“完整状态可靠落盘”分开，避免频繁传输大文件。

## Codex / MCP 入口

```powershell
npm.cmd run canvas:mcp
```

MCP 工具：

| 工具 | 用途 |
| --- | --- |
| `get_starbridge_canvas_selection` | 读取当前画布选中的形状和图片资产信息 |
| `insert_starbridge_canvas_image` | 把本地图片复制进当前页面资产目录，并插入到画布 |

旧的 `get_cowart_selection`、`insert_cowart_image` 和 `COWART_*` 环境变量仍作为迁移兼容别名保留。

## 版本边界

- 画布状态默认写到 `<project>\canvas\`，该目录不进入 Git。
- 画布只操作用户指定项目目录，不扫描用户主目录。
- 实时事件只传形状类型、id 和计数，不传完整画布内容。
- 图片插入只复制用户显式传入的本地图片路径。
