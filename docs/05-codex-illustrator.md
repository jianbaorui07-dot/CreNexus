# 5. Codex 接入 Illustrator / AI 矢量文件

## Related research package

- [Codex + Adobe AI integration map](adobe-ai-agent-integration-map.md)
- [Illustrator vector line rebuild pipeline](illustrator-vector-line-rebuild-pipeline.md)
- [Vector rebuild example scripts](../examples/illustrator_bridge/vector_rebuild/README.md)
- [Reference image vector reconstruction quality protocol](reference-image-vector-reconstruction.md)
- [Vector short-Chinese command language](vector-command-language.md)
- [Color-faithful vectorization protocol](color-faithful-vectorization.md)

这份文档说明 Adobe Illustrator 和 `.ai` 矢量文件桥的真实状态。这里的 **AI 文件** 指 Adobe Illustrator 的 `.ai` 矢量工程文件，不是“大模型 AI”。当前主推路线是[精确像素矢量重建](exact-pixel-vectorization.md)：把原始 RGBA 像素确定性地重建为矩形复合路径，复读验证 SVG 后在 Illustrator 中存储为 AI；普通图片转矢量不使用 Image Trace。受控原生 Image Trace 协议和 headless OpenCV 量化 fallback 仍保留用于兼容、研究和既有 schema 测试。

公开仓库只描述接入方式、参数化脚本方向和安全边界，不上传客户图稿、源图路径、导出结果或私有 `.ai` 工程。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 精确像素→SVG | `examples/illustrator_bridge/scripts/exact_pixel_vector.py` | 主推入口；不缩放、不量化、不嵌入位图、不使用 Image Trace；连续同色像素合并为矩形并按 RGBA paint 合并复合路径 |
| manifest | `examples/illustrator_bridge/bridge.json` | 声明状态、入口、支持任务和安全说明 |
| 环境探测 | `examples/illustrator_bridge/probe.ps1` | 检查 Illustrator 环境和 COM 线索 |
| 总状态探测 | `examples/bridge_status.py` | 检查 `ILLUSTRATOR_EXE` 和 `Illustrator.Application` COM |
| 当前文档信息 | `examples/illustrator_bridge/scripts/document_info.ps1` | 只读当前打开文档的名称、画板、图层和对象数量 |
| 只读 preflight | `examples/illustrator_bridge/scripts/preflight_plan.py` | 对脱敏文档摘要做链接、颜色模式、文本对象风险检查，不打开 `.ai` |
| headless 彩色位图→SVG | `examples/illustrator_bridge/scripts/trace_photo_preview.py` | 显式输入 PNG/JPEG；输出背景 `<rect>` + 可编辑 `<path>` 的纯矢量 SVG、PNG 预览、联系表和带 hash 的产物清单；不需要 Illustrator |
| SVG 产物验证 | `examples/illustrator_bridge/scripts/svg_artifact_verifier.py` | 要求 XML/尺寸有效、非空路径、无嵌入位图/脚本/外链；失败不发布半成品 |
| sandbox 画板 demo | `examples/illustrator_bridge/scripts/create_demo_artboard.ps1` | 默认 dry-run；确认后创建公开安全测试 `.ai` |
| sandbox 导出 demo | `examples/illustrator_bridge/scripts/export_demo_assets.ps1` | 确认后只从 demo 文档导出 SVG、PNG 和 PDF |
| 彩色矢量化协议 | `protocols/color_vectorization.v1.schema.json` | 固定授权、彩色描摹参数、质量闸门和本地安全边界 |
| 彩色验收证据协议 | `protocols/color_vector_comparison.v1.schema.json` | 固定脱敏哈希、尺寸、ICC 状态、轮廓、色差、SSIM 和矢量 hard gates |
| 彩色 Image Trace | `scripts/color_vectorize.ps1` + `jsx/color_vectorize.jsx` | 默认 dry-run；双确认后只处理明确传入的单张 PNG/JPEG，输出 AI/SVG/PNG 到 sandbox |
| demo manifest | `examples/illustrator_bridge/write_demo_manifest.py` | 汇总本地 demo 输出，manifest 本身不提交 |

## 图片如何直接变成矢量图（主推）

生成已验证 SVG 不需要 Illustrator，只需要 Pillow：

```powershell
python -m pip install -e ".[illustrator-vector]"
npm.cmd run illustrator:vectorize:offline -- --input "<input.png>" --reference-id "reference"
```

默认输出在被 Git 忽略的 `examples/output/illustrator/exact-pixel/<reference-id>/`。每个 RGBA 像素都由矩形几何覆盖，连续同色像素按行合并，随后按 paint 合并为复合 path。报告不写源图路径和文件名。

SVG 通过验证后，在 Illustrator 中打开 `exact_pixel_vector.svg` 并存储为 `.ai`。禁止点击“图像描摹”。复杂照片会产生数十万到数百万矩形子路径，保存 AI 时应等待 Illustrator 完成并核对文件存在。完整过程、上限和脱敏本机写入摘要见[精确像素矢量重建](exact-pixel-vectorization.md)。

旧量化 SVG 命令保留为兼容实验，但不作为默认路线：

```powershell
npm.cmd run illustrator:vectorize:legacy-quantized -- --input "<input.png>" --commit-preset flat_16
```

旧量化 CLI 适合扁平插画、图标和色块稿预处理。SVG 验证除证明“确实产生了可编辑路径且没有偷偷嵌入原图”，还会用受限本地 rasterizer 把最终 SVG 的纯色 `rect/path` 回栅格，并分开报告两组指标：`svg_raster_quality` 对比本轮内存量化目标，用于证明矢量几何没有额外丢色；`reference_svg_quality` 对比应用 EXIF 方向和尺寸限制后的显式输入工作 RGB，用于暴露调色、量化、轮廓简化和小区域丢弃造成的整体偏差。两组都只返回像素完全匹配率、平均绝对误差和归一化相似度，不返回像素、文件名或路径。相似度低于 `0.95` 时只标记 `review_required`，不得冒充视觉通过；复杂照片、渐变、透明度、文字、ICC 严格色差和细小拓扑仍需在 Illustrator 中人工复核。

## Illustrator 桌面链路需要什么

- 已授权可用的 Adobe Illustrator desktop。
- Windows PowerShell。
- 可用的 `Illustrator.Application` COM。
- 如需 Python COM 探测，需要 pywin32。
- 如需本地彩色预览验收，需要安装 Adobe extra：`python -m pip install -e ".[adobe]"`。

真实路径只放本机环境变量：

```powershell
$env:ILLUSTRATOR_EXE="<path-to-Illustrator.exe>"
```

## 验证命令

```powershell
npm.cmd run status:probe:json
```

直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\probe.ps1
python examples\bridge_status.py --probe-executables --json
python examples\illustrator_bridge\scripts\preflight_plan.py --json
python -m unittest tests.test_color_vectorization
python -m unittest tests.test_color_vector_repair
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\scripts\color_vectorize.ps1
python -m unittest tests.test_illustrator_color_trace -v
```

## 推荐 MCP 工具方向

| 工具名 | 作用 | 当前状态 |
| --- | --- | --- |
| `illustrator.document_info` | 读取当前文档名称、画板数量、尺寸、颜色模式、图层和对象数量 | 已有只读脚本 |
| `illustrator.create_demo_artboard` | 创建公开安全测试画板和基础矢量对象 | 已有 sandbox demo，默认 dry-run |
| `illustrator.preflight` | 对脱敏文档摘要做只读 preflight，不打开 `.ai` | 已实现 metadata-only |
| `illustrator.color_vectorize_plan` | 生成 Photoshop / Illustrator 应用矩阵、彩色描摹参数和质量闸门 | 已实现，纯内存 dry-run |
| `illustrator.color_vectorize_backend_plan` | 在原生 Illustrator 与 headless SVG fallback 间做保守选择 | 已实现，纯内存 dry-run；不探测环境、不执行 CLI |
| `illustrator.color_vectorize_validate` | 校验调用方提供的轮廓、色差、感知相似度和节点统计 | 已实现，不读取图片 |
| `illustrator.color_vectorize_compare` | 比较明确授权参考图与 sandbox PNG，自动计算 ICC、轮廓、色差、SSIM 和矢量证据 | 已实现，只读两个明确文件，不返回路径、像素或元数据 |
| `illustrator.color_vectorize_repair_plan` | 把脱敏 compare findings 编译为最多三轮的确定性 Image Trace 参数修复计划 | 已实现纯内存计划；输出 execute dry-run 模板、post-execute compare 契约与明确停止条件 |
| `illustrator.color_vectorize_execute` | 对明确传入的 PNG/JPEG 执行固定 Image Trace，输出 AI/SVG/PNG | 已实现受控本地原型，默认 dry-run、双确认 |
| `exact_pixel_vector.py` | 原始 RGBA 像素→矩形复合 path→已验证 SVG | 主推 standalone CLI；不是 MCP tool；后续由 Illustrator 存储为 AI |
| `trace_photo_preview.py` | headless 色彩量化与轮廓化，真实生成并复读无嵌入位图 SVG | 旧兼容实验；不是默认图片转矢量入口 |
| `illustrator.export_demo_assets` | 从 sandbox demo 文档导出 SVG、PDF 和 PNG | 已有 sandbox demo，需显式确认 |
| `illustrator.run_demo` | 创建测试画板、导出 demo 产物并生成 manifest | 已有一键流程，需显式确认 |

旧规划名 `trace_image_to_vector` 已拆分为 plan / validate / compare / repair_plan / execute 五个入口，避免把只读计划、自动验收、受限修复规划和真实写入混在一个高风险工具里。

## 不能做什么

- 普通图片转矢量任务不能选择 Image Trace；必须使用精确像素矢量重建，超过安全上限时停止并交还用户。
- 既有 Image Trace 协议结果不能直接声称为“原样通过”；真实输出必须先看 PNG 预览并通过外部质量指标。
- headless CLI 只是实验性色彩量化与多边形轮廓，不承诺照片级曲线、渐变、透明度或文字保真，也不能替代原生 Image Trace。
- 产物验证只证明文件结构、可编辑路径和非嵌入位图，不证明视觉等价或生产质量。
- 不能提交 `.ai` 私有工程、客户图稿、商业字体、商业画笔、购买素材。
- 不能提交源图路径、微信临时路径、桌面路径、导出目录和真实项目输出。
- 不能提交 Illustrator 安装路径、Creative Cloud 缓存、账号、许可证、Cookie 或 token。
- 不能自动登录、绕过授权或批量抓取账号内云文档。

## 同类项目对比与差距（2026-07-14）

| 项目 | 可借鉴能力 | StarBridge 当前差距 |
| --- | --- | --- |
| [VTracer @ `fd9cdb0`](https://github.com/visioncortex/vtracer/commit/fd9cdb08e622f237eb05be553a020ddc9e4c47a1) | MIT、无 GUI、彩色高分辨率、stacked/cutout、polygon/spline、poster/photo 预设 | headless OpenCV fallback 只有调色板量化和多边形；缺少平滑曲线、照片模式与更成熟的层次策略。VTracer 是后续候选，但其进程成功也仍需经过同一 verifier。 |
| [ImageTracerJS @ `cb0c84a`](https://github.com/jankovicsandras/imagetracerjs/commit/cb0c84a309df5e75614d3b5166cdc77a56f12a98) | 浏览器/Node 彩色 tracing；测试会统计 SVG bytes、路径数和像素差异 | headless fallback 已补 bytes/hash/path/color 与最终 SVG→量化目标的像素差异证据；它仍不是原始参考图↔最终 SVG 的视觉等价证明，不能与原生 PNG compare 混作同一证据。 |
| [Inkscape @ `e76072a`](https://gitlab.com/inkscape/inkscape/-/commit/e76072ae5ae7d2ab77886450102d4d5e245834ac) | Potrace/Autotrace/libdepixelize、彩色多扫描、中心线与编辑器内结果 | 适合作为已安装编辑器的 fallback；`object-trace` 的完成文本不能证明有路径，仍须解析最终 SVG。StarBridge 尚未接入。 |

本轮只补 headless 小闭环：固定 K-means 随机种子、用 `evenodd` 复合路径保留超过最小面积阈值的孔洞、验证真实 SVG 并提供事务式发布恢复；若自动恢复本身失败，旧产物备份会留在忽略输出目录供人工恢复。原生 Image Trace 的 plan / validate / compare / repair_plan / execute 保持不变；VTracer 与最终 SVG 回栅格视觉差异分别留给后续独立小轮次。

## 下一步

1. 保留 `examples/bridge_status.py` 的 Illustrator 状态检查入口。
2. 继续把 demo 输出保持在 `examples/output/illustrator/`，不提交真实生成物。
3. 为原生 Image Trace 补用户授权公开样例的真实桌面 E2E 证据；未运行前继续明确标注。
4. 用 `next_execute_template` 驱动 execute dry-run；真实执行仍需显式确认，随后按 `post_execute_compare` 绑定明确参考图、sandbox PNG 和 trace evidence，达到轮次上限后停止，不自动重复桌面写入。
5. 评估 VTracer 作为 headless 可选高质量后端，仍复用当前 SVG verifier 和产物清单。
6. 后续为 `reference_svg_quality` 增加 ICC/alpha/轮廓/SSIM 等严格指标；当前只比较解码后的工作 RGB，并与原生 PNG compare 分开报告。
7. 扩展 preflight 检查，例如字体替换风险、颜色空间和链接资产风险。
8. 所有桌面软件真实写入继续要求 dry-run 之后显式确认。
