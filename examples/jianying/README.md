# 剪映 / CapCut 草稿计划示例

这个目录只演示安全的 `draft_plan` 生成流程，不会写入真实剪映或 CapCut 草稿目录。

## 生成安全草稿计划

```powershell
python examples\jianying\generate_draft_plan.py
```

脚本会读取 `sample_timeline_spec.json`，生成：

```text
examples/jianying/output/draft_plan.json
```

该文件是计划 JSON，不是剪映真实草稿。里面只包含占位素材标识，不包含真实图片、视频、音频、客户文件或本机路径。

## 安全边界

- 不读取真实剪映草稿。
- 不写入真实剪映草稿目录。
- 不启动剪映或 CapCut。
- 不调用云渲染。
- 不下载素材。

真实草稿写入必须在后续独立能力中显式实现，并且需要用户确认草稿目录、素材授权和备份策略。
