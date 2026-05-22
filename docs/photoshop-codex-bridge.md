# Codex 接入 Photoshop 本地桥

更新时间：2026-05-22

这份文档把本机 Photoshop 实验整理成可公开协作的项目方案。仓库只记录通用脚本、协议和安全边界，不记录任何个人路径、安装路径、源图路径、桌面路径、账号信息、素材文件名或授权信息。

## 当前结论

Codex 接入 Photoshop 可以分成三层：

| 层级 | 方式 | 用途 | 当前建议 |
| --- | --- | --- | --- |
| 最小可用 | Windows COM + Photoshop JavaScript | 连接已打开的 Photoshop、创建测试文档、导出 PNG、调用主体选择 | 先作为本地实验入口 |
| 可交互面板 | Adobe UXP 插件 | 在 Photoshop 面板里读取文档信息、触发本地桥请求 | 等安装 UXP Developer Tool 后推进 |
| MCP 工具层 | 本地 HTTP/WebSocket/MCP 服务 | 让 Codex 用工具调用 Photoshop 批处理能力 | 等 COM/UXP 行为稳定后封装 |

本机实验已经验证过：Codex 可以通过 Windows COM 调用 Photoshop 的脚本接口，创建测试文档并导出 PNG；也可以用 Photoshop 的主体选择能力做抠图实验。复杂海报、文字背景、纹理背景会影响主体选择质量，所以抠图脚本只能作为半自动起点，必要时还要人工修边或增加二次蒙版清理。

## 仓库入口

| 文件 | 用途 |
| --- | --- |
| `examples/photoshop_bridge/README.md` | Photoshop 本地桥实验说明 |
| `examples/photoshop_bridge/scripts/com_probe.ps1` | 连接 Photoshop COM，创建测试文档并导出 PNG |
| `examples/photoshop_bridge/scripts/extract_subject_to_png.ps1` | 打开输入图，调用 Photoshop 主体选择，导出透明 PNG |
| `examples/bridge_status.py` | 增加 Photoshop 状态检查，只读取通用环境和 COM 可用性 |

## 运行条件

- Windows。
- 已授权可用的 Photoshop。
- Python 状态脚本可选使用 `pywin32/win32com` 读取已运行的 Photoshop COM 对象。
- PowerShell 脚本通过 `Photoshop.Application` COM 对象连接 Photoshop。
- 需要 UXP 面板时，再安装 Adobe UXP Developer Tool。

不要把以下内容写进仓库：

- Photoshop 私有安装路径。
- Creative Cloud 账号、许可证、缓存、Cookie、token。
- PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- 本机源图路径、桌面路径、临时输出路径。
- 任何需要登录、订阅、验证码、OAuth 或账号审批的过程截图。

## 最小验证流程

先手动打开 Photoshop，然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

这个脚本会：

1. 连接已安装的 `Photoshop.Application` COM 对象。
2. 用 Photoshop JavaScript 创建测试文档。
3. 写入测试文字。
4. 导出 PNG 到传入的 `OutputPath`。
5. 返回 JSON，供 Codex 或日志系统读取。

## 抠图实验流程

只在你明确提供输入图和输出路径时运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

这个脚本会：

1. 打开输入图。
2. 调用 Photoshop 的 `autoCutout` 或 `selectSubject`。
3. 将选区复制成新图层。
4. 隐藏原背景。
5. 按透明区域裁切。
6. 导出透明 PNG。

注意：主体选择不是万能抠图。人物、产品、纯背景通常效果较好；复杂海报、文字贴近主体、背景线稿穿过主体时，需要二次清理。

## 后续优化

- 把 COM 探针结果写入本地 HTTP 桥，形成 `127.0.0.1` 只读状态接口。
- 增加 UXP 面板：读取当前文档名称、尺寸、图层数量，并发送到本地桥。
- 增加半自动抠图后处理：保留最大主体、羽化边缘、清理背景残留。
- 把稳定命令封装成 MCP 工具，例如 `photoshop_get_document_info`、`photoshop_create_probe_doc`、`photoshop_extract_subject`。
- 所有会修改图像的命令默认只输出新文件，不覆盖原图。

## 官方资料

- Adobe UXP for Photoshop: https://developer.adobe.com/photoshop/uxp/
- Adobe UXP Developer Tool: https://developer.adobe.com/photoshop/uxp/2022/guides/devtool/
- Photoshop UXP API: https://developer.adobe.com/photoshop/uxp/ps_reference/
- Photoshop UXP Scripting: https://developer.adobe.com/photoshop/uxp/ps_reference/media/uxpscripting/
