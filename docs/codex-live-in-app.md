# Codex 在创作软件内可视化运行

目标是让操作者留在 Photoshop、Illustrator 或 AutoCAD 中，就能同时看到 Codex 的当前步骤和实际画布变化，而不是再打开一个独立看板。

## 运行方式

```text
Codex / MCP
  ├─ 结构化命令 ─→ 本机 Node 代理 ─→ Photoshop / Illustrator UXP ─→ 画布
  │                                  └→ Codex Live 面板
  └─ CAD 命令 ─────────────────────→ AutoCAD COM ─→ 画布 + 命令行提示
```

- Photoshop：`Codex Live` UXP 面板显示阶段、步骤、进度、执行方式和更新时间。
- Illustrator：StarBridge 面板内新增相同的 `Codex Live` 区域。
- AutoCAD：状态进入已打开文档的命令行/提示区，绘图实体按原 COM 工作流逐步出现并刷新视口。
- 软件内步骤只显示脱敏文字，不包含本机路径、客户文件名或素材内容。

面板状态是“Codex 正在做什么”的说明，不是写入成功证据。最终结果仍以软件画布、图层/对象状态和导出证据为准。

## 发布一条状态

下面命令默认只校验并打印，不连接软件：

```powershell
python scripts/publish_live_session.py --bridge photoshop --step-label "调整图层" --message "Codex 正在调整图层结构" --progress 40
```

代理和插件已经运行时，增加 `--publish` 才会把状态发进软件：

```powershell
python scripts/publish_live_session.py --bridge illustrator --step-index 2 --step-total 4 --step-label "生成路径" --message "Codex 正在生成矢量路径" --progress 50 --publish
python scripts/publish_live_session.py --bridge autocad --step-index 3 --step-total 5 --step-label "绘制尺寸" --message "Codex 正在绘制尺寸标注" --progress 60 --publish
```

Adobe 代理的每个合规 RPC 请求也会自动发送 `running` 和 `completed` / `failed` 状态，不需要额外脚本调用。
