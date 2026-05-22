# Photoshop 本地桥示例

这个目录只保存可公开的 Photoshop 接入示例。脚本不包含个人路径、素材路径、账号信息或授权信息；运行时请通过参数传入输入和输出路径。

## 前置条件

- Windows。
- 已授权可用的 Photoshop。
- PowerShell 可以创建 `Photoshop.Application` COM 对象。
- 运行前建议先手动打开 Photoshop，避免脚本触发不受控的启动流程。

## COM 探针

创建一个测试文档并导出 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

返回结果为 JSON，包含 Photoshop 版本、输出路径、文档尺寸和图层数。

## 主体抠图

从输入图里尝试提取主体，并导出透明 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "D:\path\source.jpg" -OutputPath "$env:TEMP\subject.png"
```

脚本使用 Photoshop 的主体选择能力。复杂海报、文字背景、线稿背景可能会带出背景残留，适合作为半自动起点，不保证一次达到商业级精修。

## 安全边界

- 不覆盖原图，只输出新文件。
- 不提交输入图、输出图、PSD、字体、笔刷、素材库或账号信息。
- 不把本机路径写入仓库文档或脚本默认值。
- 需要登录、授权、插件确认、验证码时，由人手动完成。
