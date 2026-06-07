# Photoshop Hard-Task Success Patterns

更新时间：2026-06-07

本文只记录对第三方参考仓的结构研究，不复制第三方源码，不把第三方实现并入 StarBridge。

## 本机参考仓

- `.codex/references/photoshop-python-api-mcp-server`
- `.codex/references/photoshop-mcp`

这两个目录仅用于本机对照，已通过 `.gitignore` 忽略，不进入 GitHub。

## 对照目标

这次研究只回答一个问题：StarBridge 要怎样提高 Photoshop hard-task 的成功率，同时不突破公开仓的安全边界。

## 观察到的可借鉴模式

### 1. 会话层和操作层要分开

`photoshop-python-api-mcp-server` 明显把 session、document、layer 等能力拆开。这个做法的价值不是“工具越多越好”，而是把读取当前状态和真正修改文档区分开。

对 StarBridge 的启发：

- 保留 `photoshop.session_info` / `photoshop.document_info` 作为只读层。
- 不直接把任意图层编辑、任意文件打开暴露成 MCP tool。
- hard-task 先走 recipe 规划，再决定是否进入真实执行。

### 2. registry 要先表达边界，再表达能力

`photoshop-mcp` 的价值不在具体命令细节，而在 tool registry、session、server 分层很清楚，适合拿来对照“能力声明”和“执行器”分离。

对 StarBridge 的启发：

- 先在 `tool_registry` 里声明 `recipe_list / plan / validate / run / debug`。
- 让 `safe_default`、`requires_confirmation`、`requires_local_software` 先说清楚风险。
- 把 dry-run 规划结果和真实执行结果分成两个返回面。

### 3. hard-task 不该先暴露低层任意动作

第三方仓里常见的是“文档、图层、效果”细粒度工具很多。这种模式适合私有本机自动化，不适合 StarBridge 当前公开仓。

原因：

- 一旦开放任意 PSD 打开、任意 JSX、任意导出路径，安全边界马上失守。
- hard-task 真正需要的不是更多低层命令，而是更稳定的受控流程。

所以 StarBridge 这次采用 Recipe Layer，而不是继续新增原子 Photoshop 写工具。

## StarBridge 采用的最小安全吸收

### 保留

- 只读 session/document 能力
- sandbox demo create/export/run 流程
- `examples/output/photoshop` 输出边界
- `dry_run=true` 默认值
- `confirm_write=true` 的显式确认门槛
- EvidenceManifest / validation / debug 返回面

### 不吸收

- 任意 PSD 路径打开
- 任意 ExtendScript / JSX 执行
- 任意本地目录扫描
- 自动登录、授权绕过、验证码绕过
- 写出到桌面、下载目录或用户自定义绝对路径
- 第三方仓中的具体实现代码

## 这次落地到 StarBridge 的结构

新增五个 MCP tool：

- `photoshop.recipe_list`
- `photoshop.recipe_plan`
- `photoshop.recipe_validate`
- `photoshop.recipe_run`
- `photoshop.recipe_debug`

其中：

- `recipe_list` 只列出受审查 recipe。
- `recipe_plan` 只返回 dry-run 计划、输出清单、质量门。
- `recipe_validate` 只校验 sandbox、脱敏和 manifest 形状。
- `recipe_run` 默认仍是 dry-run；真实执行必须 `confirm_write=true`。
- `recipe_debug` 只给 retry policy 和故障排查建议。

## 为什么这比直接加更多 Photoshop tool 更稳

- Codex 先拿到结构化 recipe，再决定是否执行，减少误调用。
- 输出文件被提前声明，便于检查是否越界。
- real run 被压缩到现有 sandbox demo 脚本，不额外扩张攻击面。
- 测试可以覆盖 schema、registry、dry-run、refusal、path sandbox、redaction，而不用在 CI 启动 Photoshop。

## 当前仍不支持

- 打开用户私有 PSD
- 对任意图片做生产级自动修图
- 任意脚本注入
- 任意导出目录
- 在 CI 中真实启动 Photoshop
