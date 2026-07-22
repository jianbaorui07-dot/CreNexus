# 3. Codex 接入 Photoshop

这份文档说明 Photoshop 桥的真实状态。当前仓库已有诊断、COM 探针、当前文档信息读取、主体抠图实验、本机接入报告和 sandbox PSD/layer demo，状态是 `experimental demo available`。它还不是稳定的生产级修图自动化工作流。

公开仓库只保存通用协议、参数化脚本和安全边界，不保存 Photoshop 安装路径、账号、授权信息、PSD、素材路径、源图文件名或桌面输出路径。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 本机诊断 | `examples/photoshop_bridge/scripts/diagnose_local.ps1` | 检查安装线索、COM 注册、进程和可选 COM 探测 |
| 只读探针 | `examples/photoshop_bridge/probe.ps1` | 输出安全的 probe report |
| 当前文档信息 | `examples/photoshop_bridge/scripts/document_info.ps1` | 读取当前文档名称、尺寸、模式和图层数量 |
| sandbox PSD demo | `examples/photoshop_bridge/scripts/create_demo_document.ps1` | 默认 dry-run；确认后创建公开安全测试 PSD 和命名图层 |
| sandbox preview export | `examples/photoshop_bridge/scripts/export_demo_preview.ps1` | 确认后只从 demo PSD 导出 PNG / JPG preview |
| Camera Raw tuning plan | `ps.camera_raw.tune` / `examples/photoshop_bridge/plans/camera_raw_tune_blue_artwork.example.json` | 默认 dry-run，只验证蓝色织物/蓝晒类作品照片的调色参数计划 |
| 矢量描摹预处理 | `photoshop.recipe_run` + `prepare_vector_trace` | 默认 dry-run；双确认后只在 sandbox 副本上做 sRGB、限尺寸和可选中值降噪，再交给 Illustrator |
| demo manifest | `examples/photoshop_bridge/write_demo_manifest.py` | 汇总本地 demo 输出，manifest 本身不提交 |
| COM 探针 | `examples/photoshop_bridge/scripts/com_probe.ps1` | 创建测试文档并导出 PNG |
| 主体抠图实验 | `examples/photoshop_bridge/scripts/extract_subject_to_png.ps1` | 输入和输出路径都由参数传入 |
| 智能多实例分层 | `.codex/skills/starbridge-smart-cutout-ps/` | 每个可见主体独立透明图层，最终由 Photoshop 原生保存并重开验收 |
| 本机接入报告 | `examples/photoshop_bridge/write_practice_report.py` | 汇总诊断、实操结果和 PNG 元数据 |
| 四联海报实验 | `examples/photoshop_bridge/experiments/4up_hex_poster/run_4up_hex_poster.ps1` | 生成参数化 JSX；本机完整执行会调用 Photoshop COM |

## 智能抠图 PS Skill

仓库内 Skill `$starbridge-smart-cutout-ps` 处理“每栋楼一个图层”“每个物体分别抠图”等多实例请求。它把每个可见主体导出为全画布透明 PNG，用优先级消除相邻蒙版重叠，并验证背景、未分配前景和所有主体恰好覆盖每个源像素一次。

公开的匿名化多楼体范例在 `.codex/skills/starbridge-smart-cutout-ps/references/skyline-instance-layering.md`；实例规格模板在同目录的 `instance-layer-spec.example.json`。仓库不保存示例原图、真实楼体坐标、模型文件名或生成结果。

先生成本地图层和 manifest：

```powershell
python .codex\skills\starbridge-smart-cutout-ps\scripts\export_instance_layers.py `
  --input "<explicit-input-image>" `
  --spec "<client-approved-instance-spec.json>" `
  --out-dir "examples/output/photoshop/smart-cutout-job" `
  --model "<explicit-local-segmentation-model-file>" `
  --confirm-write
```

检查 `preview/layer-index.jpg` 与 `preview/cutout-preview.png` 后，再由 Photoshop 原生构建、保存并重新打开：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .codex\skills\starbridge-smart-cutout-ps\scripts\build_instance_psd.ps1 `
  -ManifestPath "examples/output/photoshop/smart-cutout-job/manifest.json" `
  -OutputPath "examples/output/photoshop/smart-cutout-job/editable.psd" `
  -ConfirmWrite `
  -OpenAfterBuild
```

只有返回 `validated_after_reopen=true`，且 Photoshop 中图层数量、尺寸和可见性符合预期，才算 PSD 完成。第三方解析器能读取 PSD 不能替代这项验收。

## 需要本机安装什么

- 已授权可用的 Adobe Photoshop desktop。
- Windows PowerShell。
- 可用的 `Photoshop.Application` COM。
- 如需 Python COM 探测，需要 pywin32。

真实路径只放本机环境变量或本地 `.env`：

```powershell
$env:PHOTOSHOP_EXE="<path-to-Photoshop.exe>"
```

运行前建议手动打开 Photoshop，避免脚本触发不受控启动流程。

## 验证命令

```powershell
npm.cmd run photoshop:diagnose
# Use recipes e.g. remove_background, enhance_portrait etc. with action_plan for plan-then-execute
npm.cmd run photoshop:recipe:plan -- --recipe_id remove_background --action_plan
```

直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1 -ProbeCom
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
```

单独运行 COM 探针：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

主体抠图实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

生成本机接入报告：

```powershell
python examples\photoshop_bridge\write_practice_report.py --run-practice
```

报告会记录环境诊断、COM 探测、当前文档、一键实操和图片产物清单，包括 PNG 是否存在、文件大小、图片尺寸、透明像素统计、主体边界和 SHA256 摘要。

sandbox demo 命令：

```powershell
# Use recipes e.g. remove_background, enhance_portrait etc. with action_plan for plan-then-execute
npm.cmd run photoshop:recipe:plan -- --recipe_id remove_background --action_plan
npm.cmd run photoshop:demo
npm.cmd run photoshop:manifest
```

真实输出只写入 `examples/output/photoshop/`，生成的 PSD、PNG、JPG 和 manifest JSON 不提交。

Camera Raw tuning 是实验能力。V1 支持参数规划和安全验证；真实 Photoshop apply 需要先用 Alchemist 或 Photoshop Action listener 录制并审查本机 BatchPlay descriptor，并且必须显式传入 `confirm_apply=true`。当前没有已审 descriptor fixture 时，`dry_run=false` 会返回 `camera_raw_batchplay_descriptor_not_recorded`，不会自动拖动 Camera Raw 弹窗滑块，也不会修改 Photoshop。

可复用协议 schema：

```powershell
python -m json.tool examples\photoshop_bridge\protocols\camera_raw_tune.v1.schema.json
```

示例计划：

```powershell
python -m json.tool examples\photoshop_bridge\plans\camera_raw_tune_blue_artwork.example.json
```

Codex 调用脚本：

```powershell
python examples\photoshop_bridge\scripts\camera_raw_tune.py --source-path "<user-provided-raw-file>" --exposure 0.5 --contrast 8 --highlights 20 --shadows -6 --whites 20 --blacks -7 --texture 11 --vibrance 12 --basename blue_artwork_tuned --export-after-apply --write-plan --write-xmp
```

这个脚本只走 `ps.camera_raw.tune` 参数协议。默认 dry-run，不读取私有 RAW，不写桌面；计划和 XMP sidecar 预览输出固定在 `examples/output/photoshop`。

确认执行本机 Photoshop COM 导出：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\camera_raw_export.ps1 -InputPath "<user-provided-raw-file>" -Basename blue_artwork_tuned -Exposure 0.5 -Contrast 8 -Highlights 20 -Shadows -6 -Whites 20 -Blacks -7 -Texture 11 -Vibrance 12 -ConfirmApply -ConfirmExport
```

该脚本只处理用户显式传入的 RAW，并先复制到 `examples/output/photoshop` 再写同名 XMP 和导出 JPG；不写桌面，不修改原始目录。

四联科技六边形海报实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1 -GenerateOnly
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\experiments\4up_hex_poster\run_4up_hex_poster.ps1
```

该实验会本地生成分层 PSD、白底 PNG、透明 PNG 和预览 JPG。公开仓库只保留生成脚本、模板和 `sample_verification_report.json`，不保留实际输出图或本机路径。

## 不能做什么

- 不能提交 Photoshop 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能提交 PSD 私有工程、商业字体、商业笔刷、购买素材、客户图片。
- 不能提交源图路径、桌面路径或导出结果。
- 不能承诺复杂商业海报、复杂文字背景、线稿背景都能自动抠好。
- 不能把实验脚本说成稳定生产级工作流。
- 不能把自动实例蒙版说成无需复审的语义正确结果。
- 不能自动控制 Camera Raw modal UI 鼠标拖动；只能走结构化计划和已审 BatchPlay descriptor。
- 复杂商业修图、主体抠图和真实项目 PSD 仍然需要人工确认。

## 下一步

1. 稳定只读 `document_info`。
2. 用公开测试图实测 `prepare_vector_trace` 的 sRGB、透明度与 JPEG 降噪结果，并继续用自动色差门验收。
3. 增加二次蒙版、最大主体保留、边缘羽化和人工确认流程。
4. 评估 UXP 面板和本地 MCP 工具层。
5. 保持输入和输出路径都由参数传入，不写默认个人路径。

## Photoshop Recipe DSL 与批处理闭环

本次新增四个只读类型化入口：

- `ps.capabilities`：把 session、document、layers、selection/mask、adjustments、smart objects、text、history、export 分开标注为 `implemented / experimental / planned`；工具存在不等于真实 Photoshop 已连接。
- `ps.recipe.compile`：编译 `simple-tone-export-v1`、`production-subject-delivery-v1`、`batch-production-delivery-v1` 及规划中的智能对象 Recipe，返回执行入口、最小或高级能力面、确认门、检查点和质量门。
- `ps.batch.plan`：为真实 `photoshop-production-v1` 工作流生成单 Photoshop host FIFO、确定性 item ID、幂等键和已完成 item 续跑计划；规划中的智能对象任务会进入 `blocked_planned`，不会排进执行队列。
- `ps.result.verify`：验收 sandbox 副本、原图未覆盖、前后状态回读、产物 SHA-256 和 Photoshop 原生重开；失败时最多允许三轮局部修正。

`simple-tone-export-v1`、`production-subject-delivery-v1` 和 `batch-production-delivery-v1` 统一路由到已有的真实 `photoshop-production-v1` 管理型工作流；该工作流具备源 hash、复制后处理、画布与基础调色、主体导出、PNG/JPEG/PSD 交付、暂存提升和产物 hash 验证。请求 PSD 时，UXP 必须重新打开暂存 PSD 并验证尺寸后才允许代理提升为最终产物。`product-composite-verified-v1` 和批量智能对象 Recipe 会如实列出仍为 `planned` 的类别并返回 `execution_ready=false`。

`ps.get_state` 只有 COM 或 UXP 实时回读成功时才返回成功，绝不把 mock 状态作为证据。`ps.get_preview` 只读取同一 `job_id` 下由 `ps.preview.export` 生成且 EvidenceManifest 标记 `real_output_verified=true` 的预览；不存在真实预览时返回不可用，不生成伪 base64。
