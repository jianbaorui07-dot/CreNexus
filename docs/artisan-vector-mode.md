# 匠心矢量：少锚点人工设计感重建

匠心矢量是建立在智能、轻量和精确三种基础模式之上的高级功能。它不追求把更多像素变成更多路径，而是尝试像设计师一样选择必要锚点：该直的地方保留角点，该顺的地方使用三次贝塞尔曲线，用更少锚点描述更清楚的形状。

旧模式和旧命令不会被删除或覆盖。匠心模式使用独立的 `artisan` 参数值和测试，并按迭代提交持续上传。

## 第一轮实现

```text
授权 PNG/JPEG
→ 减色与透明度分级
→ 小区域清理
→ 连通颜色轮廓
→ 高密度轮廓采样
→ 自适应锚点简化
→ 角点 / 平滑点分类
→ 直线 + 三次贝塞尔混合路径
→ 轮廓误差复核
→ 必要时恢复锚点重新拟合
→ 安全 SVG + 预览 + 报告
```

圆弧和连续轮廓使用 `C` 三次贝塞尔段；明显转折保留为角点，相邻角点之间使用 `L`。SVG 验证器只接受绝对 `M`、`L`、`C`、`Z`，继续拒绝位图、脚本、外链、相对命令和越界坐标。

## 验收指标

| 指标 | 含义 |
| --- | --- |
| `points` | 实际锚点数量，不把贝塞尔控制柄冒充锚点 |
| `control_points` | 三次贝塞尔控制点数量 |
| `curve_segments` | 三次贝塞尔曲线段数量 |
| `line_segments` | 直线段数量 |
| `baseline_polygon_anchors` | 同一处理轮廓使用基础多边形方案时的锚点基准 |
| `anchor_reduction_ratio` | 相对基础多边形减少的锚点比例 |
| `mean_contour_error_px` | 采样轮廓到拟合路径的平均距离 |
| `maximum_contour_error_px` | 最差采样点的轮廓距离 |
| `curve_error_tolerance_px` | 当前画布允许的自适应误差门槛 |

测试要求匠心样例必须包含真实 `C` 曲线，锚点少于基础多边形锚点，并且最大轮廓误差不超过报告阈值。

## 使用

```powershell
python -m pip install -e ".[vectorization]"
python -m starbridge_mcp.vectorization.cli `
  --input "<input.png>" `
  --mode artisan `
  --reference-id "artisan-sample"
```

桌面端选择“匠心矢量”即可使用同一引擎：

```powershell
npm.cmd run vector-app:start
```

## 迭代路线

1. **Iteration 1：几何匠心。** 少锚点、角点保护、贝塞尔曲线和误差门槛。
2. **Iteration 2：语义 AI 分层。** 识别主体、眼睛、纹样、文字、背景等设计角色，再决定路径层级和细节预算。
3. **Iteration 3：风格先验。** 针对 Logo、水墨、年画、线稿和装饰纹样建立不同锚点与曲率规则。
4. **Iteration 4：设计师交付。** Illustrator 图层、路径命名、颜色组、可编辑描边与人工修订建议。

匠心模式的长期目标不是声称“一键等同人工设计”，而是用可验证的锚点数量、轮廓误差、结构分层和可编辑性，逐轮缩小与专业设计师手工矢量稿之间的差距。
