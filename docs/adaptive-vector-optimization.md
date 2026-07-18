# 最少锚点、高相似度的自适应矢量优化

Artisan 模式在原有几何重建之后增加一个本地高级精修阶段。优化目标不是单独“简化路径”，而是在最终 SVG 实际渲染通过质量门的前提下，依次减少锚点、子路径和文件体积。Exact、Smart、Lightweight 的参数、输出和执行分支不进入该优化器。

## 质量预设

| 预设 | 结构差异 | 归一化 MAE | 边缘 Dice | 合格后的选择顺序 |
| --- | ---: | ---: | ---: | --- |
| `high-fidelity`（默认） | ≤ 15% | ≤ 0.06 | ≥ 0.92 | 锚点、子路径、文件大小、耗时 |
| `balanced` | ≤ 20% | ≤ 0.08 | ≥ 0.88 | 锚点、子路径、文件大小、耗时 |
| `minimal` | ≤ 25% | ≤ 0.10 | ≥ 0.84 | 锚点、子路径、文件大小、耗时 |

`--target-difference` 可在 5%–30% 内覆盖预设的结构差异目标；MAE 和边缘 Dice 仍使用所选预设。手动锚点预算是优化目标，不会降低视觉质量门。没有合格候选时保留原 Artisan 基准，失败候选只标记为 `preview-only`。

## 执行顺序

1. 先生成原有 Artisan 基准 SVG，并立即保存为 `artisan_baseline.svg`，作为回退点。
2. 以最长边不超过 256 px 的图像金字塔层规划候选和误差热区。
3. 从稀疏轮廓开始搜索不同简化容差；只有形状 ID、父子层级、孔洞、子路径数和角色拓扑与基准一致的候选才进入评分。
4. 每个候选都渲染完整的 `vector.svg`。低分辨率指标只参与规划，正式质量门使用原输入分辨率的最终 SVG 渲染结果。
5. 稀疏候选未通过时，只把最大残差热区内的形状恢复为高保真几何，不全图回退。
6. 候选通过后，逐个尝试撤销局部恢复；撤销后仍通过三项质量门才保留删点结果。
7. 建立 Pareto 候选集；正式候选按锚点、子路径、文件大小、耗时排序。优化结果的锚点不会多于已通过质量门的基准。

规则几何使用专门的最少锚点拟合：圆和椭圆使用四个三次贝塞尔锚点，矩形保留四个角点，矩形孔洞保留内外轮廓各四个角点；拟合仍须通过轮廓距离、面积、拓扑和最终渲染质量门。

连续两轮结构差异改善不足 0.2 个百分点、锚点变化不足 1% 时提前停止。最多允许两个候选并行；当前确定性实现按顺序执行，因此同样满足该上限。

## 最终 SVG 评分

本地渲染器只接受已经通过仓库验证器的安全 `M/L/C/Z` 路径 SVG，并拒绝位图、Base64、外链、脚本和不受支持的样式。正式指标包括：

- `difference_percent`：由最终渲染 SSIM 换算的结构差异；
- `normalized_mae`：白底合成后的 RGB 归一化平均绝对误差；
- `edge_dice`：带 1 px 容差的双向边缘 Dice；
- `alpha_mae`：透明通道误差，仅作报告，不替代前三个硬门槛。

`preview.png` 仍是编辑预览，不作为正式相似度证据。`svg_render.png` 才是最终 SVG 的原输入分辨率渲染证明。

## CLI 与 API

```powershell
python -m starbridge_mcp.vectorization.cli `
  --input "<input.png>" `
  --mode artisan `
  --quality-preset high-fidelity `
  --target-difference 15 `
  --anchor-budget auto `
  --resource-budget auto `
  --compact
```

新增参数：

```text
--quality-preset high-fidelity|balanced|minimal
--target-difference 5..30
--anchor-budget auto|1000..120000
--resource-budget low|auto|high
--detail-protection 0..1
--no-auto-minimize-anchors
--compact
```

`RunConfig` 和桌面应用使用相同字段。桌面应用的手动锚点预算滑杆采用 1,000–120,000 的对数映射。

## 本地缓存与资源边界

缓存键由输入 SHA-256、SVG SHA-256、质量参数、渲染器版本和输出尺寸共同组成。候选渲染、指标和误差热图保存在忽略目录 `examples/output/vectorization/.adaptive-cache/`，不会进入 Git。

`auto` 默认取当前可用内存的 25%，上限 1.5 GiB。最终原分辨率验证的保守内存估算超限时，任务在发布前以 `resource_limit` 停止，不覆盖已有成果，也不会启动 Illustrator。

## 输出与紧凑引用

Artisan 额外输出：

```text
artisan_baseline.svg          可回退的原 Artisan 结果
svg_render.png                最终 SVG 原输入分辨率渲染证明
adaptive_optimization.json   候选、质量、缓存和停止原因报告
```

完整报告记录候选数量、Pareto 集、最终渲染指标、锚点变化、缓存命中率、资源预算和停止原因。`--compact` 返回小于 2 KB 的 `quality_ref`、`edit_ref`、`patch_ref`、指标摘要和最多五个误差热区，不返回像素、完整路径、原图数据或私有绝对路径。第一版完全本地执行，`external_ai_calls` 固定为 `0`。

Illustrator 不参与候选生成和评分。只有正式质量门通过后，用户才可通过现有确认式 Illustrator 事务流程打开或应用结果。
