# CreativeTransaction 协议

`CreativeTransaction` 是 StarBridge 跨软件 Recipe 的统一执行契约。它先把用户意图、风险、审批点、质量门和恢复策略固化为可审查数据，再允许后续 bridge 请求执行。

## 安全默认值

- 新事务始终从 `draft` 状态开始。
- 默认 `dry_run=true`，不读取私有素材，不启动桌面软件。
- `L2` 及以上风险必须声明审批点。
- 模型策略使用 `frontier` / `balanced` / `fast` 能力别名，不在 Recipe 中锁定厂商模型 ID。
- 状态迁移使用 allowlist；不允许跳过验证、审批或视觉复核。

## 风险等级

| 等级 | 含义 | 示例 |
| --- | --- | --- |
| `L0` | 静态发现 | tool list、schema |
| `L1` | 只读观察 | 脱敏 session 摘要 |
| `L2` | dry-run / sandbox 预览 | Recipe plan、预览导出 |
| `L3` | 已确认的本地写入 | 写入忽略的 output 目录 |
| `L4` | 高影响或不可逆动作 | 默认拒绝，不进入自动化 |

## 状态链

```text
draft -> planned -> validated -> awaiting_approval -> approved
      -> running -> verifying -> completed
                         |          |
                         v          v
                    repair_needed  failed / aborted
```

Recipe Plan 目前只返回事务预览，不持久化、不执行。后续 MCP 执行工具必须在 schema、tests 和确认门完整后再接入。
