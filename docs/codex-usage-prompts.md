# Codex 调用 StarBridge 的标准提示词

这些提示词用于未来让 Codex、Cursor、Claude Code 或其他 MCP 客户端调用 StarBridge。当前仓库优先支持状态检查；写入、导出和脚本执行类提示词必须等对应工具实现后再使用。

## 通用状态检查

```text
请调用 StarBridge 的 status 工具，检查所有本地创意软件 bridge 的状态。只输出统一 JSON 摘要：ok、bridge、action、message、warnings、next_steps。不要打开任何用户文件，不要读取素材目录。
```

```text
请检查 StarBridge 中的 <bridge-name> bridge 是否可用。bridge-name 可以是 comfyui、photoshop、illustrator、blender、autocad、jianying_capcut。只做只读探测；如果未安装或未启动，请用 warnings 和 next_steps 说明。
```

## ComfyUI

```text
请通过 StarBridge 检查 ComfyUI bridge。确认 API 是否可访问、/system_stats 是否可读、/object_info 是否可读，以及基础节点是否存在。不要提交 workflow，不要读取模型文件，不要输出生成图片路径。
```

## Photoshop

```text
请通过 StarBridge 检查 Photoshop bridge。只确认 PHOTOSHOP_EXE、pywin32/win32com 和 Photoshop.Application COM 线索。不要打开 PSD，不要读取源图路径，不要导出文件。
```

```text
当 Photoshop read_document_info 工具可用后，请读取当前活动文档的安全摘要：尺寸、颜色模式、图层数量。不要输出文件系统路径，不要读取客户素材内容。
```

## Illustrator

```text
请通过 StarBridge 检查 Illustrator bridge。只确认 ILLUSTRATOR_EXE、pywin32/win32com 和 Illustrator.Application COM 线索。不要打开 .ai 私有工程，不要读取链接图片路径，不要导出文件。
```

```text
当 Illustrator read_document_info 工具可用后，请读取当前文档的安全摘要：画板数量、尺寸、颜色模式、文字对象数量、链接状态。不要输出源图路径或导出目录。
```

## Blender

```text
请通过 StarBridge 检查 Blender bridge。只确认 BLENDER_EXE、blender 是否在 PATH 中、可选 BLENDER_MCP_DIR 是否存在。不要打开 .blend 文件，不要下载外部模型，不要渲染。
```

## AutoCAD / CAD

```text
请通过 StarBridge 检查 AutoCAD bridge。只确认 cad-mcp-autocad 子项目、AUTOCAD_EXE、win32com 和 COM 线索。不要打开 DWG/DXF，不要写真实项目输出。
```

```text
当 AutoCAD export_result 工具可用后，优先生成离线 DXF 到本机忽略目录；只有用户明确确认后，才调用真实 AutoCAD COM 或 MCP 绘图动作。
```

## 剪映 / CapCut

```text
请通过 StarBridge 检查 jianying_capcut bridge。只确认 JIANYING_EXE、CAPCUT_EXE、JIANYING_DRAFTS_DIR、CAPCUT_DRAFTS_DIR 是否配置和存在。不要读取 draft_content.json，不要导出视频，不要触碰账号。
```

## 严格模式

```text
请用 StarBridge strict 模式做 CI 风格检查。如果任一 bridge 未通过，应返回失败退出码；但仍要输出 JSON，说明每个 bridge 的 warnings 和 next_steps。
```

## 安全要求

每次调用 StarBridge 都应遵守：

- 不输出真实用户目录、安装目录、素材目录、模型文件名、账号、token、Cookie。
- 普通 `--json` 用于交互式状态检查，即使某些 bridge 未配置也应返回 exit code 0，并通过 `ok=false`、`warnings`、`next_steps` 说明。
- `--strict` 用于 CI 或合并门禁，任一 bridge 未通过时可以返回 exit code 1。
- 不提交或读取 PSD、AI、DWG、DXF、剪映草稿、模型、生成图片、导出视频。
- 需要登录、授权、验证码、订阅或 OAuth 时停止，让用户手动处理。
- 写入类动作必须要求用户显式传入输入路径和输出路径。
- 第一台电脑只维护 StarBridge 核心 status/probe、schema、sanitizer 和合并准备；不要扩展 ComfyUI 或剪映 / CapCut bridge，避免和第二台电脑冲突。
