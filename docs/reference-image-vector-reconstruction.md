# 参考图片矢量重建协议

## 核心业务

用户明确提供一张有权使用的参考图片，智能体将其重建为视觉接近、结构可编辑、可交付的矢量图。

这不是单纯 Image Trace，也不以像素逐点一致为唯一目标。系统必须同时保证：

1. 主体轮廓、比例、负形和遮挡关系接近参考图。
2. 输出保持为有语义的路径、图层、文本和 symbol，而不是一块嵌入图像。
3. 路径节点数可控，重复元素可复用，设计师可继续编辑。
4. 画板、颜色模式、字体、出血和导出格式满足交付条件。

## 输入边界

- 只处理用户明确传入的图片或公开测试样例。
- 不扫描私有素材目录，不搜索本机历史工程。
- 输入摘要只保留尺寸、色彩、hash、用户授权声明和脱敏 basename。
- 默认只生成 plan 和质量报告；写入 SVG 或 Illustrator sandbox 需显式确认。

## 重建流程

```text
reference image
  -> semantic decomposition
  -> VectorSceneGraph
  -> geometry/topology validation
  -> SVG or Illustrator sandbox render
  -> preview capture
  -> five-dimension quality evaluation
  -> VectorPatch repair plan
  -> final evidence
```

### 1. 语义拆解

拆分画板、主体、内部负形、特征线、文字、装饰、颜色 token 和重复组件。优先识别遮挡关系与对称、对齐、固定比例等几何约束。

### 2. 结构化重建

智能体先输出结构化 Scene Graph，再交给确定性 geometry engine 转换为 SVG 或 Illustrator typed operations。不允许模型直接生成任意脚本并在 Illustrator 中执行。

### 3. 预览与修复

每轮只读取当前事务生成的 sandbox preview，并生成基于 object id 的 `VectorPatch`。修复默认最多两轮；超过预算后返回 `needs_user`，不无限循环。

## 五维质量模型

| 维度 | 权重 | 主要检查 |
| --- | ---: | --- |
| `geometry` | 28% | 轮廓、比例、对齐、对称、间距 |
| `topology` | 24% | 闭合路径、负形、孔洞、遮挡、自交 |
| `editability` | 18% | 节点数、分层、live text、symbol 复用 |
| `visual` | 20% | 色彩、层级、构图、可读性、视觉平衡 |
| `production` | 10% | 画板、出血、颜色模式、字体、导出格式 |

评分范围为 `0..100`。默认通过条件：

- 加权总分不低于 `90`。
- 任一维度不低于 `75`。
- 严重发现数为 `0`。
- 所有 hard gate 通过。

Hard gate 至少包括：

- `reference_authorized`：用户已声明有权使用参考图。
- `primary_silhouette_present`：主体轮廓存在。
- `topology_valid`：应闭合的路径已闭合，无非预期自交。
- `editable_vector_present`：存在可编辑矢量对象，不是嵌入原图伪装交付。
- `safe_output_scope`：输出仅位于 sandbox / ignored output。

## 判定级别

| verdict | 条件 |
| --- | --- |
| `pass` | 总分、最低维度、hard gates 和严重发现全部通过 |
| `repair_needed` | hard gates 通过，但质量分数或非严重发现未达标 |
| `blocked` | hard gate 失败或存在严重发现 |

## 证据要求

Evidence 只保存：

- 脱敏 reference id 和 hash。
- Scene Graph 版本和对象数量摘要。
- 每轮 preview hash。
- 五维分数、hard gates、findings 和 verdict。
- VectorPatch 的 object id 和操作摘要。

不保存原图绝对路径、Illustrator 安装路径、账号状态、客户素材或真实导出文件。

## 当前实现边界

本协议描述的是“语义结构重建”路线；目前仍只提供公开质量报告 schema、确定性 Scene Graph 编译和纯离线评分器，本身不读取图片、不打开 Illustrator，也不声称已完成语义自动重建。

另有独立的[彩色参考图矢量化协议](color-faithful-vectorization.md)，已提供默认 dry-run 的本地 Illustrator Image Trace 原型。它负责固定参数描摹与 sandbox 导出，不等同于本协议的语义分层重建；输出仍需视觉比较，未通过前保持 `needs_visual_review`。

后续语义重建 MCP tool 必须在 Scene Graph、VectorPatch schema、视觉验证和 sandbox 确认链完整后再接入。

短华语词汇、默认值和冲突规则见 [矢量短华语指令协议](vector-command-language.md)。
