# 彩色参考图矢量化协议

## 目标

用户明确提供一张有权使用的 PNG 或 JPEG 后，StarBridge 生成视觉接近原图、可在 Illustrator 继续编辑的本地矢量副本。默认输出 SVG、Illustrator sandbox 文档和 PNG 预览；原图、绝对路径与真实输出都不进入 Git。

“原样”在这里表示通过轮廓、颜色和感知相似度闸门，而不是承诺任意照片都能做到逐像素一致。照片、纹理、透明叠加和复杂渐变可能产生大量路径；此时应保留 `needs_visual_review`，或改用语义重建 / hybrid 路线。

## 应用矩阵

| 阶段 | 软件 | 默认行为 | 写入边界 |
| --- | --- | --- | --- |
| 输入授权 | Codex / StarBridge | 只接受用户本次明确传入的单个文件，不扫描目录 | 只记录脱敏 `reference_id` 和 hash |
| 可选预处理 | Photoshop | 默认关闭；需要时仅对副本做色彩空间归一、轻度去噪或尺寸准备 | 只能写 `examples/output/photoshop/` |
| 彩色描摹 | Illustrator | RGB、fills、2–256 色、保留白色、生成 swatches | 只能写 `examples/output/illustrator/` |
| 矢量展开 | Illustrator | `redraw` 后读取 trace 指标，再 `expandTracing(false)` | 不保留嵌入原图冒充矢量 |
| 预览与验收 | Illustrator + StarBridge | 导出 PNG 预览；外部比较器回传轮廓、Delta E、感知相似度 | 未达阈值只返回 `repair_needed` |

Photoshop 不是强制步骤。已经是颜色稳定、分辨率合适的图片应直接交给 Illustrator，避免无意义的重复编码。Photoshop 预处理执行器尚未公开时，计划只标注该阶段，不会假装已经运行。

## 四个 MCP 入口

### `illustrator.color_vectorize_plan`

纯内存计划，不读取图片、不启动 Adobe 软件、不创建目录。它输出固定应用矩阵、Image Trace 参数、质量阈值和安全边界。`reference_authorized=true` 是硬条件。

### `illustrator.color_vectorize_execute`

默认 `dry_run=true`。真实执行同时要求：

- `reference_authorized=true`；
- 明确的单个 `input_path`，扩展名只能是 `.png`、`.jpg` 或 `.jpeg`；
- `confirm_write=true` 与 `confirm_export=true`；
- 输出留在 `examples/output/illustrator/`；
- 本机已有授权且正在运行的 Illustrator；
- 只运行仓库内固定、可审计的 JSX，不接收任意 JSX / eval。

执行结果只报告脱敏 reference id、输入 hash、描摹统计和仓库相对输出，不回显输入路径或文件名。完成 SVG / AI / PNG 生成后仍标记 `needs_visual_review`，直到比较指标通过。

### `illustrator.color_vectorize_validate`

只校验调用方提供的脱敏指标，不读取图片。默认闸门：

| 指标 | 默认阈值 |
| --- | ---: |
| `silhouette_iou` | `>= 0.96` |
| `aspect_ratio_error` | `<= 0.02` |
| `mean_delta_e` | `<= 4` |
| `p95_delta_e` | `<= 10` |
| `perceptual_similarity` | `>= 0.95` |
| `anchor_count` | `<= 200000` |

授权、主轮廓、拓扑、可编辑矢量或安全输出任一 hard gate 失败时返回 `blocked`；hard gate 通过但视觉或复杂度指标未达标时返回 `repair_needed`。

### `illustrator.color_vectorize_compare`

本地读取用户本次明确传入的参考 PNG/JPEG，以及 `examples/output/illustrator/` 中由执行器生成的候选 PNG。它不会扫描目录，也不读取 `.ai`、SVG、PSD 或链接素材。候选路径解析后必须仍位于 Illustrator sandbox；符号链接逃逸同样会被拒绝。

比较步骤固定为：

1. 检查授权、单文件类型、文件大小和像素上限。
2. 如图片带嵌入 ICC profile，使用 Pillow `ImageCms` 转到 sRGB D65；profile 无效时明确报告 fallback。
3. 按参考图宽高比缩放到有界工作尺寸，报告原始宽高和 `aspect_ratio_error`，不保存归一化像素。
4. 透明图用 alpha 建轮廓；不透明图用四角背景色估计前景，计算 `silhouette_iou`。
5. 在有界采样上计算 CIE76 Delta E 的 mean / p95，并计算 8×8 block SSIM 作为 `perceptual_similarity`。
6. 合并 Image Trace 返回的节点、用色、开放路径和残留 raster 证据，直接输出 `pass`、`repair_needed` 或 `blocked`。

安全要求：

- `reference_authorized=true` 之前不打开任何图片。
- 参考图只能是明确文件，候选只能是 sandbox PNG。
- 参考与候选 hash 完全相同时按“可能把原图复制成候选”阻断，不能伪装成矢量复核通过。
- JSON 只返回 SHA-256、尺寸、方法、指标和判定；不返回 basename、绝对路径、ICC profile 名称、EXIF 或像素。
- Pillow 不可用时返回 `verdict=blocked` 与结构化 `comparison_unavailable`，不把缺依赖当成通过。

本地 Adobe 视觉比较依赖：

```powershell
python -m pip install -e ".[adobe]"
```

颜色管理依据 Pillow [ImageCms](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html)；Lab 转换遵循 [CSS Color 4 的 D65 / Lab 转换](https://www.w3.org/TR/css-color-4/#color-conversion-code)。block SSIM 是有界、可复现的自动闸门，不替代设计师对细节、渐变和纹理的最终查看。

## Image Trace 参数

本地执行器只开放 Adobe 文档明确支持的参数：

- `max_colors`: 2–256；
- `path_fitting`: 0–10，越小越贴近像素轮廓；
- `min_area`: 最小被描摹区域；
- `preprocess_blur`: 0–2；
- `ignore_white`: 默认 `false`，保留原图中的白色；
- `output_to_swatches`: 默认 `true`；
- `fills=true`、`strokes=false`、`tracingMode=TRACINGMODECOLOR` 固定不变。

Illustrator 的 tracing 是异步操作，固定 JSX 会在读取 `anchorCount`、`pathCount`、`areaCount` 和 `usedColorCount` 前调用 `app.redraw()`，然后才展开矢量。参考：[TracingOptions](https://ai-scripting.docsforadobe.dev/jsobjref/TracingOptions/)、[TracingObject](https://ai-scripting.docsforadobe.dev/jsobjref/TracingObject/)。

## 同类方案取舍

- Adobe 官方云端 [Image Trace API](https://developer.adobe.com/firefly-services/docs/illustrator/guides/image-trace/) 支持 `enhanced_general` 和 `high_fidelity_photo`，但输入必须放在预签名 URL，且要轮询云端任务。仓库不把私有素材上传云端，因此它只作为未来显式 opt-in 路线，不是默认实现。
- [krVatsal/illustrator-mcp](https://github.com/krVatsal/illustrator-mcp) 能直接发送 ExtendScript 并截图，覆盖面广；StarBridge 不开放任意脚本和全屏截图。
- [ie3jp/illustrator-mcp-server](https://github.com/ie3jp/illustrator-mcp-server) 提供较丰富的读取、修改与导出工具；StarBridge 的公开仓库边界更窄，不读取链接素材、字体内容或客户工程。

当前差距不再是“没有 Image Trace 入口”或“没有可计算预览证据”，而是 Photoshop 预处理真实执行和自动 VectorPatch 修复还未贯通。后续增强必须继续遵循文档 → schema → tests → 安全实现顺序。

## 验证

```powershell
python -m unittest tests.test_color_vectorization
python -m unittest tests.test_mcp_tools_adobe tests.test_mcp_tool_schemas
python -m starbridge_mcp.mcp_server --list-tools
```

没有用户明确提供的公开图片时，只能验证 schema、计划、拒绝路径和脚本静态边界；不得声称已在 Illustrator 中完成视觉验收。
