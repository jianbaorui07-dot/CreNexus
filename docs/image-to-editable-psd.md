# 图片智能分层与可编辑 PSD

这条流水线把用户明确传入的一张扁平图片重建成便于人工修正的 PSD。它不会声称恢复不存在的原始图层，而是生成可审计的语义图层、补全背景、质量报告和低置信复审包。

## 可复用过程，而不是示例图特化

标准工作流固定为七步：

1. `plan` 只读分析图片类型，并生成客户问题和推荐的 `starbridge.layer_intent.v1`。
2. 客户先确认最常修改的内容、主体粒度、文字策略、背景补全需求，以及是否允许记录无像素决策样本。
3. `run --intent-json ... --require-intent` 根据明确意图执行本地分层；未提供意图时只能使用带警告的保守默认值。
4. 系统输出统一的 `manifest.json`、图层 PNG、蒙版、复审小图和质量报告。算法不会直接控制 Photoshop。
5. 复审只返回版本化差异补丁；确定性代码修改 manifest 或局部 Alpha。
6. Photoshop Builder 按 manifest 组装 PSD，保存后重新打开并验收结构。
7. 只有客户显式同意时，复审选择才写为本地、无像素、无源路径的 JSONL 决策样本，供后续规则校准或预训练使用。

这套流程的可复用合同是“背景、主体、文字、装饰、原图参考、QA”六类角色，不依赖某一张线稿、海报或某个具体 IP。图像策略可以不同，manifest、复审补丁、PSD Builder 和验收报告保持一致。

### 客户意图配置

公开模板位于 `examples/photoshop_bridge/layer_intent.example.json`。主要字段会真实影响执行：

机器可校验协议位于 `examples/photoshop_bridge/protocols/layer_intent.v1.schema.json` 和 `examples/photoshop_bridge/protocols/layer_review_patch.v1.schema.json`；未知字段、越界置信度和任意代码字段都会被拒绝。

- `subject_granularity`：整体主体、主要实例或语义组；选择整体主体时不会产生无意义的细分候选。
- `text_policy`：高置信时重建 Photoshop 文字层、只保留文字像素层，或不处理文字。
- `background_policy`：补全遮挡区域，或有意识地保留原始背景像素。
- `decoration_policy`：显著装饰独立成层，或保留在主体中。
- `review_budget`：限制复审裁剪图总量和每批激活数量。
- `learning.record_decisions`：默认 `false`；只有明确改为 `true` 才记录决策特征。`include_pixels: true` 会被程序拒绝。
- `feedback.github_metrics_upload`：默认 `false`；客户明确同意后，任务结束可向固定 GitHub Issue 或 Discussion 追加一条匿名指标评论。`include_customer_content: true` 会被程序拒绝。

意图配置的规范化结果和哈希会进入 manifest 与缓存键。同一图片只要客户目标不同，就会产生新的任务结果；相同图片、相同意图和相同算法版本才能安全命中缓存。

### GitHub Issues / Discussions 匿名反馈

反馈传输只在 `run`、`patch`、`build` 和 `batch` 完成后触发；`plan` 和公开合成 `regression` 永远不上传。默认关闭，必须同时满足：

1. 客户意图中 `feedback.github_metrics_upload: true`。
2. `consent_version` 等于 `starbridge.github_metrics.v1`。
3. `include_customer_content` 保持 `false`。
4. 本机显式配置 collector 目标，并已由客户自行完成 `gh auth login`。

Issue 模式会向一个固定 Issue 追加评论，不会每次新建 Issue：

```powershell
$env:STARBRIDGE_FEEDBACK_TRANSPORT="issue_comment"
$env:STARBRIDGE_FEEDBACK_REPOSITORY="owner/repository"
$env:STARBRIDGE_FEEDBACK_ISSUE="123"
```

本仓库的真实验收 collector 是 [Issue #89](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/issues/89)。它只是公开示例，代码不会把该地址写成默认上传目标。

Discussion 模式同样只向一个固定 Discussion 追加评论；`DISCUSSION_ID` 是 GitHub GraphQL node ID，不是页面上的数字：

```powershell
$env:STARBRIDGE_FEEDBACK_TRANSPORT="discussion_comment"
$env:STARBRIDGE_FEEDBACK_REPOSITORY="owner/repository"
$env:STARBRIDGE_FEEDBACK_DISCUSSION_ID="<discussion-node-id>"
```

本仓库的 Discussion 验收 collector 是 [Discussion #90](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/discussions/90)。Issue 与 Discussion 每次只选择一种 transport，不会双重上传。

正式开启前可设置 `$env:STARBRIDGE_FEEDBACK_DRY_RUN="1"`。此时 CLI 会返回最终白名单 payload，但不会调用 GitHub。

上传字段只包括：UTC 日期粒度、匿名随机事件 ID、算法版本、策略枚举、客户意图枚举、画布方向与尺寸区间、四项质量分数、图层/区域数量和成功/缓存状态。发送前会递归拒绝任何图片、像素、裁剪图、OCR 内容、语义名称、文件名、源哈希、本机路径、用户名、邮箱或 token。GitHub 拒绝或网络失败只记录通用状态，不回显可能含敏感信息的 stderr，也不影响本地 PSD 交付。

机器协议为 `examples/photoshop_bridge/protocols/github_issue_metrics.v1.schema.json`。

## 当前可运行范围

- `auto` 会先在本地判断普通海报或“浅色纹理底上的红/棕线稿”。
- 普通海报第一轮拆为背景、主体、文字像素参考、可编辑文字占位、原图参考和 QA 蒙版。
- 线稿纹理图先拆出纸纹背景、构图中心圆形装饰、右下印章，再把近圆形主体分成 6–10 个互斥候选区域。
- 环形区域的分界线不是固定直线：本地动态规划会在有限角度内寻找低墨线密度路径，尽量从纸纹空隙穿过，减少切断完整笔画。
- 分界后会用高置信墨线核心检查跨层连通笔画；尺寸可控且归属明确的笔画会整体回收到主区域，大型交叉网络继续标为歧义。
- 歧义网络按影响排序并进入两阶段复审：先确认所有区域语义，再每批只激活最多 2 个局部连笔裁剪图。指定归属后仅在现有区域 PNG 之间迁移对应 Alpha，重组外观保持不变。
- 背景使用本地 inpaint 补全；主体、文字参考和装饰保持全画布坐标。
- Photoshop 按 `manifest.json` 确定性组装 PSD，不让视觉模型直接执行任意 JSX。
- 批处理按“算法版本 + 内容哈希 + 选项 + 复审输入”续跑；算法升级会自动失效旧缓存，同版本重复输入直接复用。

当前还不能保证：复杂毛发无损边缘、商业字体准确匹配、严重遮挡后的真实背景恢复，以及把相互交叠的群像自动拆成每个独立角色。群像细拆会作为后续的局部语义复审步骤，不阻塞基础 PSD 生成。

## 低 token 迭代

默认流程不把整张图反复交给模型：

1. 本地算法完成策略判断、候选遮罩、背景补全和重组评分，消耗 0 个模型 token。
2. 只有低置信文字、语义区域和按影响排序的连笔歧义才进入 `review_packet.json`。
3. 复审只发送列出的裁剪图和问题，不发送整张图。
4. 模型或人工返回 `starbridge.layer_review_patch.v1` 差异文件。
5. 文字和语义标签补丁只修改 manifest；连笔归属补丁只改指定局部的区域 Alpha 与蒙版，完整图像分析和背景都不重算。
6. 输入哈希、选项和分析哈希一致时直接命中缓存。

环形区域复审只需要逐块返回 `region_id`、简短名称、`accepted` 和置信度。系统会记录已确认数量；全部区域确认后自动关闭对应语义警告，但仍保留其他独立 QA 警告。这个过程不重新打开源图做视觉分析，也不重新生成图层素材。

区域全部确认后，`review_packet.json` 自动进入 `stroke_ambiguity_assignment` 阶段。每次最多给出 2 张局部裁剪图和其允许的 `candidate_region_ids`；返回 `component_id` 与其中一个 `target_region_id` 即可。系统完成确定性的局部 Alpha 迁移后补入下一批，直到队列清空。补丁会记录 `artifact_revision`、已解决组件数和复审后的连通笔画指标，同时验证各区域 Alpha 的并集保持不变。

这样可以把能力提升放在本地算法、Photoshop 执行器和 QA 指标上，而不是用更多对话 token 换取同一张图的重复分析。

## 命令

先做只读计划：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli plan `
  --input "<input-image>" `
  --preset auto
```

阅读输出中的 `client_questions`，复制并确认 `recommended_intent_profile`，或从公开模板开始编辑。生产执行可要求意图不可缺省：

生成分层素材和 manifest。所有输出必须留在忽略目录 `examples/output/photoshop/`：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli run `
  --input "<input-image>" `
  --output-dir "examples/output/photoshop/image-to-psd-job" `
  --intent-json "examples/photoshop_bridge/layer_intent.example.json" `
  --require-intent `
  --preset auto `
  --confirm-write
```

组装 PSD 并留在本地 Photoshop 中打开：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli build `
  --manifest "examples/output/photoshop/image-to-psd-job/manifest.json" `
  --output "examples/output/photoshop/image-to-psd-job/editable.psd" `
  --confirm-write `
  --open
```

批处理只扫描显式目录的第一层，不递归寻找私有素材：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli batch `
  --input-dir "<explicit-input-directory>" `
  --output-root "examples/output/photoshop/batch-job" `
  --intent-json "<client-approved-intent-json>" `
  --require-intent `
  --workers 2 `
  --confirm-write
```

运行不依赖私人素材的跨意图回归；它会本地生成线稿与海报输入，并验证主体细分、可编辑文字、文字像素参考和保留原始背景四种合同：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli regression `
  --output-root "examples/output/photoshop/synthetic-regression" `
  --confirm-write
```

报告只保存公开合成案例 ID、意图哈希、图层数和质量指标，不记录绝对路径。该命令也在专用 Linux/Windows CI 矩阵中执行。

复审补丁示例：

```json
{
  "schema_version": "starbridge.layer_review_patch.v1",
  "text_regions": [
    {
      "region_id": "text_01",
      "content": "已确认标题",
      "font_candidates": ["SourceHanSansCN-Bold"],
      "color": "#FFFFFF",
      "confidence": 0.94
    }
  ],
  "semantic_regions": [
    {
      "region_id": "ring_region_01",
      "name": "上方神兽_已确认",
      "semantic_label": "神兽",
      "accepted": true,
      "confidence": 0.92
    }
  ],
  "stroke_assignments": [
    {
      "component_id": "stroke_ambiguity_01",
      "target_region_id": "ring_region_01",
      "confidence": 0.9
    }
  ]
}
```

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli patch `
  --manifest "examples/output/photoshop/image-to-psd-job/manifest.json" `
  --patch "<review-patch-json>" `
  --confirm-write
```

## 公开许可数据与候选训练

公开实验不搜索或遍历客户目录，也不把测试图片提交到仓库。调用方必须先在
`examples/photoshop_bridge/public_dataset.example.json` 中逐项列出 Wikimedia Commons
文件标题和预期许可，再同时确认联网与本地写入：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli acquire-public-dataset `
  --request "examples/photoshop_bridge/public_dataset.example.json" `
  --output-root "examples/output/photoshop/public-training-pilot" `
  --confirm-network `
  --confirm-write
```

下载器只接受 `upload.wikimedia.org` 的 HTTPS 图片，限制单文件为 20 MB，并在写入前核对
Public Domain、CC0、CC BY 或 CC BY-SA。`dataset_manifest.json` 记录来源页、许可、作者、尺寸和
内容哈希，但不记录客户路径。第一轮公开试验使用了四种不同任务：

- [Animal line art drawing](https://commons.wikimedia.org/wiki/File:Animal_line_art_drawing.jpg)，Public Domain，线稿。
- [Product photo](https://commons.wikimedia.org/wiki/File:Product_photo.jpg)，CC0，产品图。
- [Pétrole Stella, advertising poster, 1897](https://commons.wikimedia.org/wiki/File:P%C3%A9trole_Stella,_advertising_poster,_1897.jpg)，Public Domain，海报。
- [Eric Lundgren - White Background](https://commons.wikimedia.org/wiki/File:Eric_Lundgren_-_White_Background.jpg)，CC0，人物图。

对许可已验证的数据，可以模拟四类客户意图并生成独立任务：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli run-public-experiment `
  --dataset-manifest "examples/output/photoshop/public-training-pilot/dataset_manifest.json" `
  --output-root "examples/output/photoshop/public-client-experiment" `
  --confirm-write
```

自动结果只标记为 `unreviewed_candidate_output`，不能直接充当训练标签。第一轮四例的重组相似度
都高于 0.995，但人工主体遮罩复核只有线稿通过；产品图存在背景布料和阴影多选，海报存在多选与
错选，人物图同时存在多选和漏选。这说明重组分数只能证明图层可重新合成，不能证明语义主体选对。
因此所有本地 GrabCut 主体候选都会进入 `subject_mask` 复审，人工通过或拒绝后才生成无像素标签。

候选训练只读取调用方逐个显式传入的 JSONL，不递归搜集文件，也拒绝 `includes_pixels` 不为
`false` 的记录：

```powershell
python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli train-subject-quality `
  --dataset "<job-01>/learning/decision_examples.jsonl" `
  --dataset "<job-02>/learning/decision_examples.jsonl" `
  --output-report "examples/output/photoshop/training/subject-quality-report.json" `
  --confirm-write
```

训练门槛固定为至少 20 个复审样本、8 个互不相同的源图组，且通过与拒绝各至少 5 个。训练集和
验证集按源图指纹分组，防止同图泄漏。当前真实试验只有 4 个源图、1 个通过、3 个拒绝，因此程序
按设计输出 `insufficient_data`：还缺 16 个样本、4 个独立源图组、4 个通过样本和 2 个拒绝样本，
不会写出模型。即使未来达到门槛，产物也固定为 `candidate_only`，
`automatic_application_allowed: false`；评分只影响复审排序，不能自动应用补丁。

公开协议位于：

- `public_image_dataset_request.v1.schema.json` 与 `public_image_dataset.v1.schema.json`：下载请求及许可清单。
- `public_client_mode_experiment.v1.schema.json`：跨类型客户模式实验报告。
- `subject_mask_training_report.v1.schema.json`：数据不足或分组验证不足报告。
- `subject_mask_quality_model.v1.schema.json`：只能用于复审建议的候选模型。

## 安全边界

- 输入只能由用户显式传入，不递归扫描私人目录。
- manifest 只记录源文件名与哈希，不记录源文件绝对路径。
- CLI 写入固定在 `examples/output/photoshop/`。
- PSD 组装必须显式 `--confirm-write`，图层素材也必须位于同一 job 目录。
- PSD、源图副本、预览和报告都已被 `.gitignore` 排除，不能提交到 GitHub。
- 决策学习默认关闭；启用后只记录归一化框、置信度、候选占比和用户选择，不记录源路径、原图或裁剪图。当前阶段是数据准备，不宣称已经训练出通用模型。

## 质量闭环

每次算法迭代都必须经过四层门禁：

1. 离线重组：把背景、主体、装饰和文字参考重新合成，记录像素 MAE、PSNR、重组相似度、主体覆盖率、背景残留和纹理保留率。
2. 语义几何：中心装饰必须同时满足构图中心距离与圆边界支持；环形候选记录区域数、互斥覆盖率、直线/弯曲边界墨线密度、跨层连通笔画变化和独立的图层可编辑性分数。
3. manifest：校验画布、固定组名、唯一图层 ID、图层类型以及所有素材路径都位于当前 job 内。
4. Photoshop：保存 PSD 后重新打开，核对画布、组数、图层数、父组、可见性、锁定状态、图层类型和非空像素边界。任一结构项不一致，构建结果即为 `ok: false`。

CI 分成两层：普通开发环境可以不安装 OpenCV；专用 `test-image-to-psd-headless` 任务会强制安装 `.[dev,image-to-psd]`，并在 Linux Python 3.10–3.13 与 Windows Python 3.12 上运行真实的“输入图 → 图层素材 → 重组预览”闭环。Photoshop 桌面回读只在本机执行，因为 GitHub runner 没有获得授权的 Photoshop。

## 后续迭代顺序

已完成：客户问题、Layer Intent Profile、意图感知缓存、分阶段小图复核、局部 Alpha 补丁、PSD 回读验收，以及可选的无像素决策样本记录。

1. 扩展公开许可回归集到至少 20 个经人工复审的主体样本和 8 个独立源图组，同时补足通过/拒绝两类标签。
2. 将连续笔画、闭合轮廓和视觉候选统一成实例候选协议；算法只产出候选与置信度，客户意图决定细拆深度。
3. 把 Photoshop 主体选择结果作为可选候选，与本地 GrabCut 候选统一评分，而不是替换本地流水线。
4. 增加文字 OCR、字体候选和描边/阴影参数重建；低置信度时继续保留像素参考层。
5. 将需要频繁替换的主体升级为智能对象，同时保留全画布坐标和原始蒙版。
6. 候选模型只有在按源图分组的未见图片验证集上稳定提升后，才能影响复审排序；自动应用仍保持关闭。

这个顺序把模型 token 留给真正的局部歧义；确定性的分割、缓存、重组、PSD 写入和验收始终留在本机执行。
