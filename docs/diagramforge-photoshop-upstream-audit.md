# DiagramForge 与 Photoshop 上游审计

审计快照日期：2026-07-22。候选仓库在仓库外隔离目录以浅克隆方式固定到下列 Commit；CreNexus 没有整仓复制，也没有复制许可证不清晰仓库的实现。

| 上游 | 固定 Commit | 许可证证据 | 可借鉴能力 | CreNexus 取舍 |
| --- | --- | --- | --- | --- |
| `jgraph/drawio-mcp` | `c3fcfa5a7227e873e9ee51451b54c291d81b0099` | 根目录 Apache-2.0 | 原生 Draw.io、嵌入 XML 导出、shape search、ELK 外部布局 | 自主实现确定性原生编译与质量门；外部 MCP/ELK 保持可选适配器 |
| `lgazo/drawio-mcp-server` | `530342d2d065ee235e81bf9b0ec15d31de1883ec` | 根目录 MIT | 多文档、多页面、图层、Live 增量编辑、单文档 FIFO | 自主实现稳定 ID、事务补丁和批计划；不复制服务端代码 |
| `jgraph/drawio-desktop` | `c2774fc6ce26c3a1bcc79771f9a3a183f275523e` | 根目录 Apache-2.0 | 离线桌面、固定 CLI 导出、安全隔离 | 仅作为可选 PDF 导出运行时，不打包二进制 |
| `alisaitteke/photoshop-mcp` | `152f8937be98b352c40ab5b525829a50d022f283` | `package.json` 声明 MIT，但固定提交没有根许可证正文 | state/preview/capabilities、Recipe、单次撤销、结构化错误 | 仅参考设计；未复制代码，等待许可证正文明确后再评估直接采用 |
| `dcc-mcp/dcc-mcp-photoshop` | `bfe375ae3ad86973c8aadad3a69d179106f81791` | `pyproject.toml` 声明 MIT，但固定提交没有根许可证正文 | 40+ 类型化工具、渐进 Skill、Sidecar/Broker、智能对象与选区 | 仅参考能力分层；CreNexus 保留 UXP/Node Proxy 安全链路，不引入 Broker |
| `loonghao/photoshop-python-api-mcp-server` | `3e317700b0b4f06f521c2efc19a0d8b376ca690d` | 根目录 MIT | Windows COM、文档/图层/session 工具 | 保留为只读 COM 回退思路，不扩大任意文件打开面 |
| `AdobeDocs/uxp-photoshop-plugin-samples` | `1928d832d9351627a319de6e341e3cfad0ef9ced` | 根目录 MIT | 官方 WebSocket、desktop helper、File I/O、BatchPlay、TypeScript 示例 | 作为 UXP 通道规范参考，继续白名单和 modal 事务 |
| `bubblydoo/uxp-toolkit` | `0e45fddc1185d9253909cffae27fe1bcb6463a44` | 固定提交无仓库级许可证声明 | 类型化 BatchPlay、CDP/UXP 开发工具 | 只研究思路；不复制代码、不启用任意 JavaScript 执行 |

## 核心差距与实现结果

| 维度 | 上游领先点 | CreNexus 本次实现 | 保留边界 |
| --- | --- | --- | --- |
| 结构化绘图 | 官方格式与 Live 编辑成熟 | DiagramForge 原生编译、稳定 ID、事务补丁、局部哈希门、质量报告、幂等批计划 | Live 编辑和 ELK 是可选外部适配器，不虚构内置连接 |
| Photoshop 工具面 | 原子工具和智能对象覆盖更广 | `ps.capabilities` 明确成熟度；可执行 Recipe 路由真实 `photoshop-production-v1`，智能对象复合 Recipe 保持 planned | planned 类别不会进入批执行队列 |
| 上下文效率 | 渐进 Skill 和 Recipe 减少调用 | `minimal` / `advanced` profile，Recipe 单历史状态与最多三轮有限修正 | 不动态加载未审计的任意脚本 |
| 批处理 | Sidecar/FIFO/队列模式 | 真实生产工作流的单 Photoshop host FIFO、确定性 item ID、幂等键、已完成 item 续跑 | 每个真实写项仍逐项确认和验收；planned 项标记 `blocked_planned` |
| 结果验收 | state/preview 回读 | `ps.get_state` 拒绝 mock 证据；`ps.get_preview` 只读真实验证产物；`ps.result.verify` 检查 sandbox、前后状态、产物哈希；生产工作流在请求 PSD 时强制 Photoshop 原生重开 | 没有真实 Photoshop 会话或真实预览时不写成通过 |
| 安全 | 多数上游偏功能覆盖 | 保留沙箱副本、路径白名单、禁止任意 Shell/JSX/BatchPlay、证据脱敏 | 不为追平工具数量降低门槛 |

## 自有创新

DiagramForge 的差异不是复刻 Draw.io MCP，而是把结构化图表纳入 CreNexus 的可审计创意任务闭环：相同语义键生成稳定 ID，局部补丁必须证明未修改区域哈希稳定，保存后重新打开验证，批任务由确定性文档哈希和 resume ID 驱动。

Photoshop 的差异是把静态能力成熟度、Recipe 编译、单主机 FIFO 批计划、有限修正和原生重开验收合并为一个 fail-closed 协议。工具“存在”与真实 Photoshop“已连接/可执行”始终分开记录。
