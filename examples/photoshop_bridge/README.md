# Photoshop 本地桥示例

这个目录只保存可公开的 Photoshop 接入示例。脚本不包含个人路径、素材路径、账号信息或授权信息；运行时请通过参数传入输入和输出路径。

## 区域一：前置条件

- Windows。
- 已授权可用的 Photoshop。
- PowerShell 可以创建 `Photoshop.Application` COM 对象。
- 运行前建议先手动打开 Photoshop，避免脚本触发不受控的启动流程。

## 区域二：本机诊断

先检查安装线索、COM 注册和进程状态：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
```

连 COM 自动化一起验证：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1 -ProbeCom
```

## 区域三：一键本机实操

运行一次完整闭环：连接 Photoshop、创建测试文档、生成公开安全测试图、执行主体抠图、输出 JSON 结果。

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
```

默认输出到：

```text
output\photoshop_bridge_practice\
```

这个目录属于本机生成物，不进入 GitHub。

## 区域四：当前文档信息

读取当前 Photoshop 文档名称、尺寸、模式和图层数量：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

## 区域五：生成本机接入报告

生成中文 Markdown 和 JSON 报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py
```

把一键实操结果也写进报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```

默认输出到：

```text
output\photoshop_bridge_report\
```

报告会列出探针图、测试输入图、主体抠图 PNG 的文件大小、PNG 尺寸、透明像素统计、主体边界和 SHA256 摘要，方便确认产物真实生成，并确认抠图结果确实有透明背景。

一键实操会先清理本轮固定产物文件，避免旧图误入报告。如果 Photoshop 临时忙碌，实操脚本会自动短暂重试；如果仍然失败，报告也会按固定文件名回收本轮已经写出的本地产物。

## 区域六：验收标准

| 检查项 | 合格标准 |
| --- | --- |
| 环境诊断 | `diagnose_local.ps1 -ProbeCom` 返回 `ready` |
| 一键实操 | `run_local_practice.ps1` 返回 `ok: true` |
| 报告留档 | `write_practice_report.py --run-practice` 生成 Markdown 和 JSON |
| 图片产物 | 产物清单中的 PNG 都存在，并显示尺寸 |
| 透明抠图 | 主体抠图 PNG 显示透明/半透明/不透明像素统计 |
| 主体边界 | 主体抠图 PNG 显示 alpha 主体边界、四边边距和主体像素占比 |
| Git 安全 | `output/` 目录没有进入 Git 提交 |

## 区域七：COM 探针

创建一个测试文档并导出 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

返回结果为 JSON，包含 Photoshop 版本、输出路径、文档尺寸和图层数。

## 区域八：主体抠图

从输入图里尝试提取主体，并导出透明 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

脚本使用 Photoshop 的主体选择能力。复杂海报、文字背景、线稿背景可能会带出背景残留，适合作为半自动起点，不保证一次达到商业级精修。

## 区域九：安全边界

- 不覆盖原图，只输出新文件。
- 不提交输入图、输出图、PSD、字体、笔刷、素材库或账号信息。
- 不把本机路径写入仓库文档或脚本默认值。
- 需要登录、授权、插件确认、验证码时，由人手动完成。
