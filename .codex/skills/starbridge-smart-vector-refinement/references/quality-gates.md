# 智能曲线精修质量闸门

## 指标定义

| 指标 | 含义 | 使用方式 |
| --- | --- | --- |
| `ssim` | 原图与“最终 SVG 实际渲染图”的结构相似度 | 越高越好；不得用量化中间预览代替 |
| `difference_percent` | `(1 - SSIM) * 100` | 初始硬门槛不高于 30%；成熟交付目标不高于 20% |
| `normalized_mae` | RGB 平均绝对误差除以 255 | 初始硬门槛不高于 0.12；成熟交付目标不高于 0.08 |
| `subpaths` | SVG 中可独立编辑的子路径数 | 过高通常意味着碎片化和 Illustrator 卡顿 |
| `anchors` | 真实锚点数量，不包含控制柄 | 必须和视觉质量一起下降，不能只追求少点 |
| `curve_segments` | 三次贝塞尔段数量 | 智能曲线候选必须大于 0 |
| `embedded_raster_count` | SVG 内嵌位图数量 | 必须为 0 |
| `external_reference_count` | 外部链接数量 | 必须为 0 |

默认复杂度闸门为 12,000 个子路径、120,000 个锚点。它们是安全起点，不是所有题材的审美标准。高密度传统纹样可在明确记录原因后调整，但不得降低纯矢量和最终渲染验证要求。

## 候选调参顺序

| 现象 | 优先调整 | 风险 |
| --- | --- | --- |
| 白缝、轮廓开裂 | 使用 `stacked` 分层；提高覆盖连续性 | paint 数可能增加 |
| 小噪点太多 | 提高 `filter-speckle` | 可能丢失细线和纹样 |
| 锚点过多 | 提高 `length-threshold` 或 `splice-threshold` | 曲线可能变钝 |
| 角点被磨圆 | 降低 `corner-threshold` 或长度简化 | 锚点增加 |
| 色块过碎 | 降低 `color-precision`，提高 `layer-difference` | 色差增加 |
| 强制少色后失真 | 撤销强制调色板，保留分层 paint | Illustrator 调色工作量增加 |

每轮只改变一个参数族，保留上一轮报告。不要用文件大小或路径数单指标选胜者。

## 推荐候选网格

以默认参数为中心生成 3-6 个候选：

```text
filter-speckle: 8 / 12 / 16
color-precision: 7 / 8
layer-difference: 4 / 6
corner-threshold: 60 / 70 / 80
length-threshold: 4 / 5 / 6
splice-threshold: 40 / 50 / 60
```

先通过安全和视觉硬门槛，再在通过者中选择更少子路径和锚点的结果。

## 失败模式

- 中间预览 SSIM 高，但最终 SVG 渲染 SSIM 明显下降：通常是相邻轮廓之间出现缝隙或变换未正确展开。
- 子路径减少但画面大块缺失：通常是碎片过滤或颜色合并过强。
- 颜色数很少但结构差异暴涨：不要把“少色”误当成“高级矢量”。
- Illustrator 只显示一个顶层图层：仍可能是纯路径，但不等于设计师语义分层。
- 文件没有位图：只证明载体真实，不能证明视觉质量或人工设计感。

## 依赖边界

候选生成器使用 MIT 许可的 [VTracer](https://github.com/visioncortex/vtracer) 作为可选曲线后端。它不等于 Illustrator Image Trace。所有原图、中间预览、渲染证明和输出报告必须留在被 Git 忽略的本地输出目录，不能提交到公开仓库。
