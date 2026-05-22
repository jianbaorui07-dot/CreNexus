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

## 区域六：COM 探针

创建一个测试文档并导出 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

返回结果为 JSON，包含 Photoshop 版本、输出路径、文档尺寸和图层数。

## 区域七：主体抠图

从输入图里尝试提取主体，并导出透明 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

脚本使用 Photoshop 的主体选择能力。复杂海报、文字背景、线稿背景可能会带出背景残留，适合作为半自动起点，不保证一次达到商业级精修。

## 区域八：安全边界

- 不覆盖原图，只输出新文件。
- 不提交输入图、输出图、PSD、字体、笔刷、素材库或账号信息。
- 不把本机路径写入仓库文档或脚本默认值。
- 需要登录、授权、插件确认、验证码时，由人手动完成。
