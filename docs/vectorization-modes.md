# 四模式图片矢量化

StarBridge 使用一个统一入口提供四种矢量化模式。原有智能、轻量和精确模式完整保留；匠心矢量作为更高定位的艺术重建模式，使用少量锚点和三次贝塞尔曲线接近人工绘制结构。所有模式都只读取用户明确传入的一张 PNG/JPEG，并输出不含嵌入位图、脚本和外链的 SVG。

## 模式

| 模式 | 默认参数重点 | 适用场景 | 是否逐像素一致 |
| --- | --- | --- | --- |
| `artisan` 匠心矢量 | 16 色、自适应锚点、设计分层；细线稿可切换为中心线、续接交叉点并按几何意图分级 | 艺术稿、品牌图形、传统纹样、高级设计交付 | 否；受轮廓、面积、中心线、续接与意图分级质量门槛约束 |
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

代理或自动化调用可增加 `--compact`，终端只返回关键指标、输出路径、`edit_ref` 和意图选择器；完整报告照常保存到输出目录，减少重复上下文和 token。

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
  artisan_edit_index.json # 仅匠心模式，代理优先读取
```

报告包含源文件 SHA-256、原始/输出尺寸、颜色、复合路径、子路径、节点、SVG 字节数、运行参数、安全验证和耗时。报告不记录源文件名或绝对路径。

匠心完整结构文件额外记录基础、主体、细节、点睛图层，稳定的 `shape-*` / `layer-*` ID、父子层级、颜色、边界框和锚点指标。第 5 轮再按局部几何分成 `flow-contour`、`ornament`、`detail` 和 `micro-detail`；这些是曲线意图，不是人物、文字或物体内容识别。

`artisan_edit_index.json` schema v2 使用紧凑数组保存选择器、形状 ID、设计师可读名称、边界框、锚点和子路径，并用 `svg_sha256` 绑定基础 SVG。后续代理优先读取它，可只检查一个局部范围：

```powershell
python -m starbridge_mcp.vectorization.artisan_edit `
  --index "<output>/artisan_edit_index.json" `
  --selector intent:ornament
```

返回值只包含 `edit_ref`、匹配对象数、合并边界框、局部锚点、设计师名称和最多 24 个形状 ID，不包含源文件名或绝对路径。Iteration 6 还可把三个客户答案编译为短 `profile_ref`，随后用 `artisan_refine` 对选中描边执行矢量到矢量局部精修并生成 `patch_ref`。完整结构、预校准和局部精修都在本地执行，`external_ai_calls` 为 `0`。

精确模式额外报告：

```text
pixel_match
different_pixel_count
maximum_channel_difference
```

正式验收要求分别为 `true`、`0`、`0`。

## 产品边界

- 智能和轻量模式是可编辑近似结果，会主动减色、清理小区域并简化轮廓。
- 匠心模式额外使用曲线拟合、设计角色层级和线稿自适应。细线稿中心线、交叉点续接和几何意图候选分别通过独立质量门；意图候选必须再减少至少 3% 子路径、锚点和总点数，编辑批次不增加，精确率/Dice 下降不超过 0.6 个百分点、召回率下降不超过 1 个百分点。失败时依次保留第 4 轮续接中心线、第 3 轮中心线或第 2 轮轮廓填充。当前角色来自本地几何推断，不宣称已经识别人脸、文字或具体物体语义。
- 精确模式保留源像素网格，但大量矩形不等同于轻量商业矢量插画。
- 当前统一核心负责 SVG、预览、参数和报告；Illustrator `.ai` 保存仍是可选桌面交付步骤，需要用户明确请求。
- 源图和生成结果只留在本地忽略目录，不能提交到公开仓库。
