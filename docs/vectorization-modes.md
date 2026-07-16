# 四模式图片矢量化

StarBridge 使用一个统一入口提供四种矢量化模式。原有智能、轻量和精确模式完整保留；匠心矢量作为更高定位的艺术重建模式，使用少量锚点和三次贝塞尔曲线接近人工绘制结构。所有模式都只读取用户明确传入的一张 PNG/JPEG，并输出不含嵌入位图、脚本和外链的 SVG。

## 模式

| 模式 | 默认参数重点 | 适用场景 | 是否逐像素一致 |
| --- | --- | --- | --- |
| `artisan` 匠心矢量 | 16 色、自适应锚点、设计分层；线稿自动切换 2 色结构 | 艺术稿、品牌图形、传统纹样、高级设计交付 | 否；受轮廓与面积门槛约束 |
| `smart` 智能矢量 | 24 色、4 级透明度、适度清理和节点简化 | 插画、海报素材、普通设计再编辑 | 否 |
| `lightweight` 轻量矢量 | 8 色、2 级透明度、更强碎片清理和简化 | Logo、图标、纹样、流畅编辑 | 否 |
| `exact` 精确重建 | 不缩放、不减色；同色扫描段横向与纵向合并 | 技术证明、RGBA 像素验证、存档 | 是 |

`balanced` 作为兼容别名会映射到 `smart`。

## 安装和运行

```powershell
python -m pip install -e ".[vectorization]"

# 默认：智能矢量
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --reference-id "sample"

# 轻量矢量
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --mode lightweight --reference-id "sample"

# 精确重建
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --mode exact --reference-id "sample"

# 匠心矢量
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --mode artisan --reference-id "sample"
```

也可以使用：

```powershell
npm.cmd run illustrator:vectorize -- --input "<input.png>" --mode smart --reference-id "sample"
```

## 桌面软件原型

安装 GUI 可选依赖并启动：

```powershell
python -m pip install -e ".[vector-app]"
vectorflow-studio

# 或
npm.cmd run vector-app:start
```

当前桌面原型提供：

- PNG/JPEG 文件选择与拖放；
- 匠心、智能、轻量、精确四种模式卡片；
- 颜色、最大尺寸、路径平滑、碎片清理和透明阈值；
- 后台工作线程，转换时界面保持响应；
- 原图与处理预览并排查看；
- 颜色、子路径、节点、SVG 大小、耗时、精确像素验证和匠心锚点减少指标；
- 打开本地输出目录。

GUI 不会上传素材，也不会自动启动 Illustrator。`.ai` 保存仍然是用户明确请求后执行的可选桌面交付阶段。

## 可调参数

```text
--max-colors
--max-dimension
--simplify-ratio
--min-region-area
--alpha-threshold
--max-subpaths
--max-points
--max-svg-size-mb
```

没有显式传入的参数由模式预设提供。安全上限被超过时，流程在发布目标文件前停止，不会自动回退到 Illustrator Image Trace。

## 输出

默认输出到被 Git 忽略的：

```text
examples/output/vectorization/<reference-id>/<mode>/
  vector.svg
  preview.png
  parameters.json
  vector_report.json
  vector_report.md
  artisan_structure.json  # 仅匠心模式
```

报告包含源文件 SHA-256、原始/输出尺寸、颜色、复合路径、子路径、节点、SVG 字节数、运行参数、安全验证和耗时。报告不记录源文件名或绝对路径。

匠心结构文件额外记录基础、主体、细节、点睛图层，稳定的 `shape-*` / `layer-*` ID、父子层级、颜色、边界框和锚点指标。`structure_ref` 是结构摘要的 12 位短引用；后续修订可以只发送结构引用、对象 ID 和修改动作，不必重新描述整张图片。结构分析完全在本地执行，报告中的 `external_ai_calls` 为 `0`。

精确模式额外报告：

```text
pixel_match
different_pixel_count
maximum_channel_difference
```

正式验收要求分别为 `true`、`0`、`0`。

## 产品边界

- 智能和轻量模式是可编辑近似结果，会主动减色、清理小区域并简化轮廓。
- 匠心模式额外使用曲线拟合、设计角色层级、线稿自适应、复合路径拆分和轮廓/面积双重检查。当前角色来自本地构图推断，不宣称已经识别人脸、文字或具体物体语义。
- 精确模式保留源像素网格，但大量矩形不等同于轻量商业矢量插画。
- 当前统一核心负责 SVG、预览、参数和报告；Illustrator `.ai` 保存仍是可选桌面交付步骤，需要用户明确请求。
- 源图和生成结果只留在本地忽略目录，不能提交到公开仓库。
