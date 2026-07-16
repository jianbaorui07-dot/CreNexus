# Illustrator / AI 矢量文件桥

这个 `prototype` 桥现在提供高定位的匠心矢量，以及完整保留的智能、轻量、精确三种基础模式，统一生成经过验证的纯路径 SVG，不使用 Image Trace。既有精确模式兼容脚本、原生 Image Trace 协议和旧 headless OpenCV 量化实验继续保留。

## 默认：智能矢量

```powershell
python -m pip install -e ".[vectorization]"
npm.cmd run illustrator:vectorize -- --input "<input.png>" --reference-id reference
```

使用 `--mode lightweight` 生成更少颜色、路径和节点；使用 `--mode exact` 执行 RGBA 像素网格重建和逐像素验证。统一输出位于 `examples/output/vectorization/<reference-id>/<mode>/`。

也可运行桌面原型：

```powershell
python -m pip install -e ".[vector-app]"
npm.cmd run vector-app:start
```

## 兼容：精确像素 SVG → Illustrator AI

```powershell
python -m pip install -e ".[illustrator-vector]"
npm.cmd run illustrator:vectorize:offline -- --input "<input.png>" --reference-id reference
```

默认输出位于 `examples/output/illustrator/exact-pixel/<reference-id>/`。在 Illustrator 中打开已验证的 `exact_pixel_vector.svg` 并存储为 `.ai`；不要执行“图像描摹”。

## Headless 彩色图直接转 SVG

先安装独立可选依赖：

```powershell
python -m pip install -e ".[illustrator-trace]"
```

再显式传入本机图片；不要把源图或输出提交到仓库：

```powershell
npm.cmd run illustrator:vectorize:legacy-quantized -- --input "<input.png>" --commit-preset flat_16
```

脚本使用固定 K-means seed 做色彩量化，并用 `evenodd` 复合轮廓保留超过最小面积阈值的孔洞，输出：

- 每个 preset 的纯矢量 SVG（背景 `<rect>` + 可编辑 `<path>`）与量化 PNG 预览；
- `trace_contact_sheet.png`；
- 可选的 `final_trace.svg` / `final_preview.png`；
- `trace_report.json`，记录仓库相对路径、bytes、SHA-256、路径数、子路径数和实际颜色数。

所有 headless 文件只写入被 Git 忽略的 `examples/output/illustrator/trace-practice/` 专用子树。生成先进入临时 staging；SVG 必须是 UTF-8、可解析、尺寸有效、至少有一个路径，并且没有 `<image>`、脚本或外链，整批才会发布。失败返回结构化 JSON；发布替换失败时自动恢复旧文件，若恢复动作本身失败则返回 `artifact_rollback_failed`，并在同一忽略输出目录保留 `.trace-recovery-*` 备份供人工恢复。

这不是 Illustrator 原生 Image Trace，也不承诺复杂照片、渐变、透明度、文字或生产级曲线保真。它当前适合扁平插画、图标和色块稿预处理。

## probe 做什么

- 检查当前系统是否 Windows。
- 检查 `ILLUSTRATOR_EXE` 是否配置并存在。
- 检查 `Illustrator.Application` COM 类型是否可用。
- 输出统一安全 JSON report。

## probe 不做什么

- 不打开客户 `.ai`。
- 不读取源图、字体、商业画笔或购买素材。
- 不保存导出结果。

## 彩色矢量化安全边界

- `protocols/color_vectorization.v1.schema.json` 固定输入授权、Image Trace 参数和质量闸门。
- `scripts/color_vectorize.ps1` 默认 dry-run；真实执行要求 `ConfirmWrite` 与 `ConfirmExport`。
- `illustrator.color_vectorize_repair_plan` 只把脱敏 findings 编译为最多 3 轮的白名单参数与默认 dry-run 的 execute/compare 安全模板，不自动执行脚本或桌面写入。
- 只连接已运行的授权 Illustrator，不接收任意 JSX，不扫描素材目录，不上传云端。
- 白色默认保留；生成结果必须经过 PNG 预览和外部指标复核，不能把 Image Trace 自动等同于“原样通过”。

## 命令

```powershell
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\probe.ps1
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\scripts\color_vectorize.ps1
python -m unittest tests.test_illustrator_color_trace -v
```

完整说明见 [`docs/color-faithful-vectorization.md`](../../docs/color-faithful-vectorization.md)。
