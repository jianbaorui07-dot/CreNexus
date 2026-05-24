# 剪映 / CapCut Bridge 方案

## 目标

剪映 / CapCut bridge 的目标是让 StarBridge 能把脚本化分镜、字幕、素材轨道和音频轨道先转换成安全的 `draft_plan`，再由后续明确授权的写入器生成真实草稿。

本轮只实现草稿计划，不写真实剪映或 CapCut 草稿目录。

## 为什么先生成 draft_plan

真实剪映草稿目录通常包含多个相互关联的 JSON、素材引用、缓存和客户端状态。直接写入可能带来：

- 覆盖用户真实草稿。
- 写入不兼容版本结构。
- 引用私有素材路径。
- 破坏剪映/CapCut 客户端缓存。

`draft_plan` 是中间层，适合先做验证、审查和测试。

## 安全边界

- `status()` 只检查环境变量和目录是否存在。
- `validate_draft_schema()` 只检查 JSON 结构。
- `create_draft_plan()` 只生成计划对象。
- `export_draft_plan()` 默认只允许写入 `examples/jianying/output/`。
- 不启动剪映或 CapCut。
- 不写真实草稿目录。
- 不调用云渲染。
- 不下载或复制真实素材。

## 草稿目录风险

环境变量 `JIANYING_DRAFTS_DIR` 或 `CAPCUT_DRAFTS_DIR` 只能用于未来只读探测。即使配置了这些变量，当前 bridge 也不会把计划导出到这些目录。

如需测试导出目录，可使用：

```powershell
$env:STARBRIDGE_JIANYING_SAFE_OUTPUT_DIR="<safe-test-output-dir>"
```

该目录必须是用户明确指定的安全测试目录，不能是剪映/CapCut 真实草稿目录。

## 后续扩展方向

- 字幕：SRT/JSON 字幕转 `draft_plan`，统一毫秒时间戳。
- 分镜：把镜头表转成 clips/texts/subtitles。
- 素材轨道：占位素材、授权素材和本地素材分开标记。
- 音频轨道：BGM、旁白、音量、淡入淡出。
- 关键帧：位置、缩放、透明度、动画曲线。
- 草稿写入器：在用户确认、备份和版本适配之后单独实现。

## 与第三方项目的关系

| 项目 | 借鉴点 | 当前处理 |
| --- | --- | --- |
| VectCutAPI | MCP 工具面、草稿管理、文字/字幕/关键帧接口 | 借鉴工具命名，不直接复制源码 |
| capcut-mate | FastAPI/OpenAPI 草稿自动化流程 | 借鉴 API 组织，不启用云渲染和对象存储 |
| cutcli-cookbook | CLI cookbook、模板、prompt 约束 | 借鉴 `draft_plan` 和示例组织，不安装外部 CLI |

StarBridge 的原则是先生成可审查计划，再进入真实草稿写入。
