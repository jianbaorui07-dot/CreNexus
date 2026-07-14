# Photoshop 本地桥示例

这个目录只保存可公开的 Photoshop 接入示例。脚本不包含个人路径、素材路径、账号信息或授权信息；运行时请通过参数传入输入和输出路径。

## 区域零：统一安全 probe

安全 probe 只检查 Windows、`PHOTOSHOP_EXE` 和 `Photoshop.Application` COM 类型，不打开 PSD，不保存图片：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\probe.ps1
```

probe report 默认写入：

```text
examples\photoshop_bridge\reports\photoshop_probe_report.json
```

`reports/` 已被 `.gitignore` 忽略。仓库只提交 `sample_report.example.json`。

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

运行一次实验闭环：连接 Photoshop、创建测试文档、生成公开安全测试图、执行主体抠图、输出 JSON 结果。

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

## 区域六：参数化海报自动化实验

`experiments/4up_hex_poster/` 保存一次公开安全的 Photoshop 四联科技六边形海报实验。目录中只提交可复跑脚本、SVG 模板和验证摘要；PSD、PNG、JPG 和运行时 JSX 都作为本机生成物忽略。

只生成 JSX 和 manifest：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1 -GenerateOnly
```

完整调用 Photoshop COM 执行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1
```

## 区域七：验收标准

| 检查项 | 合格标准 |
| --- | --- |
| 安全 probe | `probe.ps1` 返回统一 JSON report |
| 环境诊断 | `diagnose_local.ps1 -ProbeCom` 返回 `ready` |
| 一键实操 | `run_local_practice.ps1` 返回 `ok: true` |
| 报告留档 | `write_practice_report.py --run-practice` 生成 Markdown 和 JSON |
| 图片产物 | 产物清单中的 PNG 都存在，并显示尺寸 |
| 透明抠图 | 主体抠图 PNG 显示透明/半透明/不透明像素统计 |
| 主体边界 | 主体抠图 PNG 显示 alpha 主体边界、四边边距和主体像素占比 |
| Git 安全 | `output/` 目录没有进入 Git 提交 |

## 区域八：COM 探针

创建一个测试文档并导出 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

返回结果为 JSON，包含 Photoshop 版本、输出路径、文档尺寸和图层数。

## 区域九：主体抠图

从输入图里尝试提取主体，并导出透明 PNG：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

脚本使用 Photoshop 的主体选择能力。复杂海报、文字背景、线稿背景可能会带出背景残留，适合作为半自动起点，不保证一次达到商业级精修。

## 区域十：安全边界

- 不覆盖原图，只输出新文件。
- 不提交输入图、输出图、PSD、字体、笔刷、素材库或账号信息。
- 不把本机路径写入仓库文档或脚本默认值。
- 需要登录、授权、插件确认、验证码时，由人手动完成。

## 区域十一：Camera Raw 参数协议

`ps.camera_raw.tune` 使用可复用的参数协议，不控制 Camera Raw 弹窗鼠标，也不自动扫描本机图片目录。协议 schema 位于：

```text
examples\photoshop_bridge\protocols\camera_raw_tune.v1.schema.json
```

示例计划位于：

```text
examples\photoshop_bridge\plans\camera_raw_tune_blue_artwork.example.json
```

调用方可以通过 `source` 显式说明目标来自当前 Photoshop 文档或用户传入路径；V1 dry-run 只记录计划，不读取私有 RAW。真实输出目录固定为 `examples/output/photoshop`，不能写桌面或任意本机目录。

Codex 可复用脚本入口：

```powershell
python examples\photoshop_bridge\scripts\camera_raw_tune.py `
  --source-path "<user-provided-raw-file>" `
  --exposure 0.5 --contrast 8 --highlights 20 --shadows -6 `
  --whites 20 --blacks -7 --texture 11 --vibrance 12 `
  --basename blue_artwork_tuned `
  --export-after-apply `
  --write-plan --write-xmp
```

该命令默认 `dry_run=true`，只把脱敏后的调参计划写入 `examples/output/photoshop/*.camera_raw_plan.json`，并可用 `--write-xmp` 生成 `examples/output/photoshop/*.xmp` Camera Raw 参数 sidecar 预览。真实 apply/export 仍需要已审 BatchPlay descriptor，并显式传入 `--no-dry-run --confirm-apply --confirm-export`。

本地录制 Camera Raw BatchPlay descriptor 后，不要提交 fixture。把它放在本机私有位置，然后用参数或环境变量接入：

```powershell
$env:STARBRIDGE_CAMERA_RAW_DESCRIPTOR_FIXTURE="<local-verified-fixture.json>"
python examples\photoshop_bridge\scripts\camera_raw_tune.py `
  --source-path "<user-provided-raw-file>" `
  --exposure 0.5 --contrast 8 --highlights 20 --shadows -6 `
  --whites 20 --blacks -7 --texture 11 --vibrance 12 `
  --basename blue_artwork_tuned `
  --export-after-apply `
  --no-dry-run --confirm-apply --confirm-export
```

fixture 必须声明 `protocol_version: "camera_raw_tune.v1"`、`method: "ps.camera_raw.tune"`、`descriptor_kind: "camera_raw_filter"`、`verified: true` 和非空 `descriptors`。未验证 fixture 会被拒绝。

本机 Photoshop COM 导出入口：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\camera_raw_export.ps1 `
  -InputPath "<user-provided-raw-file>" `
  -Basename blue_artwork_tuned `
  -Exposure 0.5 -Contrast 8 -Highlights 20 -Shadows -6 `
  -Whites 20 -Blacks -7 -Texture 11 -Vibrance 12 `
  -ConfirmApply -ConfirmExport
```

这个脚本会先把用户显式传入的 RAW 复制到 `examples/output/photoshop`，在同目录写同名 XMP，然后通过已授权的本机 Photoshop COM 打开安全副本并导出 JPG。它不写桌面，不修改原始 RAW 所在目录。

## 区域十二：为 Illustrator 彩色描摹准备 sandbox PNG

`prepare_vector_trace` recipe 用固定 Photoshop JSX 把单张授权 PNG/JPEG 复制到 sandbox 后再处理：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\color_vector_preprocess.ps1 `
  -ReferenceId public-sample-01 -InputPath "<source-image>" `
  -MaxDimension 4096 -MedianRadius 0 `
  -ConfirmAuthorization -ConfirmWrite -ConfirmExport
```

默认不执行；缺少任一确认只返回计划或拒绝。脚本只连接已经运行的 Photoshop，不自动启动应用；输出为 `examples/output/photoshop/` 内的源图副本和 8-bit RGB PNG。中值降噪默认关闭，防止为了减少路径而无意改变原图颜色或细节。
