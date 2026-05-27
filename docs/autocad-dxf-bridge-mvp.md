# AutoCAD / DXF Bridge MVP

本 MVP 是 StarBridge 的 CAD / DXF 无头生成 bridge 原型。它的目标是先建立安全、可测试的 CAD plan 合约和 DXF dry-run 流程，而不是直接控制真实 AutoCAD。

## 为什么先做 DXF plan

直接控制 AutoCAD / DWG 会涉及本机授权、商业图纸、客户路径、COM 状态、窗口焦点和真实项目输出。DXF plan 能先把结构化几何、图层、单位和文本变成可验证数据，适合作为 Codex 后续生成 CAD 图形的中间层。

## 当前安全机制

- 默认 `dry_run=True`，不写 DXF 文件。
- 不调用真实 AutoCAD。
- 不打开 DWG。
- 不扫描用户目录。
- `dry_run=False` 时只允许写到 `examples/cad/output/`。
- 输出统一经过 StarBridge sanitizer，不输出真实用户目录。

## 支持的实体类型

| 类型 | 必要字段 |
| --- | --- |
| `line` | `start`, `end`, `layer` |
| `polyline` | `points`, `layer` |
| `circle` | `center`, `radius`, `layer` |
| `rectangle` | `x`, `y`, `width`, `height`, `layer` |
| `text` | `position`, `value`, `height`, `layer` |

## 可选依赖

`ezdxf` 是可选依赖。没有安装时：

- `status()` 仍可返回 bridge 状态。
- `validate_cad_plan()` 和 `summarize_plan()` 仍可运行。
- `write_dxf(..., dry_run=True)` 仍可运行。
- `write_dxf(..., dry_run=False)` 会返回 warning 和 next_steps，不会崩溃。

## 后续扩展

1. 把 DXF plan 接入 StarBridge 核心 server，等待核心分支合并后再注册。
2. 增加更多实体：arc、dimension、mtext、hatch。
3. 增加 AutoCAD COM 打开 DXF 的可选验证，但默认关闭。
4. 研究 AutoCAD LT File IPC，不直接依赖窗口焦点。
5. 增加 DWG 打开验证前的人为确认流程。
