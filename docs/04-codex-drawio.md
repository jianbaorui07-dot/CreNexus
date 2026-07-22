# 图枢 DiagramForge：Codex 结构化绘图

DiagramForge 是 CreNexus 新增的独立结构化绘图板块。它负责科研框架、流程图、系统架构、网络拓扑、UML、BPMN、思维导图和复杂关系图；现有 Canvas 继续负责自由构思、批注、素材摆放和灵感协同，两者不互相替代。

## 已实现能力

- 原生 `.drawio` 多页面、多图层、节点和正交连接器编译。
- 自然语言提纲、结构化 spec、Mermaid 子集和 CSV 输入。
- `research-framework-v1` 与 `system-architecture-v1` Recipe。
- 语义键生成稳定元素 ID；相同输入得到相同 ID 和文档哈希。
- `set_label`、`move`、`set_style` 差异补丁；事务提交前比较所有无关元素哈希，并保留一层可验证回滚/重做检查点。
- XML、ID、父层、连接端点、页面边界、元素重叠、文字裁切风险、文本对比度、主动 HTML 和外部图片样式检查。
- 原生 `.drawio`、内嵌 XML 的 `.drawio.svg`、manifest 和保存后重新打开验证。
- 确定性批任务 ID、幂等文档哈希、并发上限和已完成任务续跑。
- 可选 Draw.io Desktop PDF 导出；未探测到本地 CLI 时明确返回不可用，不伪造 PDF。

## 工具入口

| MCP tool | 默认行为 | 写入门 |
| --- | --- | --- |
| `drawio.probe` | 检查 headless 编译器与 Draw.io Desktop CLI | 无写入 |
| `drawio.capabilities` | 返回输入、元素、Recipe、布局和导出能力 | 无写入 |
| `drawio.plan` | 内存编译和结构验证 | 无写入 |
| `drawio.create` | 生成 `.drawio`、`.drawio.svg` 和 manifest | `confirm_write=true` |
| `drawio.inspect` | 读取一个明确的安全目录文件并返回元素哈希 | 无写入 |
| `drawio.patch` | 按稳定 ID 做局部事务修改 | `confirm_write=true` |
| `drawio.rollback` | 恢复并轮换上一层已验证检查点 | `confirm_write=true` |
| `drawio.validate` | 输出结构质量报告 | 无写入 |
| `drawio.export` | SVG headless；PDF 走固定 Draw.io Desktop CLI | `confirm_write=true` |
| `drawio.handoff.plan` | 为 Canvas、Photoshop 或 Illustrator 生成脱敏、哈希绑定的导入计划 | 无写入；下游仍需确认 |
| `drawio.batch` | 生成幂等可续跑批计划 | 无写入 |

所有路径必须是仓库相对路径，并限制在 `sandbox/`、`output/` 或 `examples/output/diagramforge/`。不会递归扫描用户目录，不会把输入来源路径写入 manifest。

## 快速验证

```powershell
npm.cmd run drawio:probe
npm.cmd run drawio:capabilities
npm.cmd run drawio:plan
npm.cmd run drawio:batch
python -m unittest tests.test_drawio_compiler tests.test_drawio_mcp
```

生成公开合成科研框架示例：

```powershell
python examples/drawio_bridge/cli.py demo --recipe research-framework-v1 --confirm-write
python examples/drawio_bridge/cli.py validate examples/output/diagramforge/research-framework.drawio
python examples/drawio_bridge/cli.py rollback examples/output/diagramforge/research-framework.drawio --confirm-write
```

运行产物受 `.gitignore` 保护，不进入 GitHub。

## 实时编辑与外部适配器

核心模块不依赖第三方服务。需要实时 Draw.io 画布时，可把官方 `@drawio/mcp` 或兼容 Live MCP 作为外部适配器；DiagramForge 继续负责 Recipe、稳定 ID、质量门、输出边界和证据。`drawio.probe` 的 `headless_compiler`、`drawio_desktop_available` 与 `live_mcp_adapter` 是三个独立真值，不能互相替代。

PDF 导出优先读取本地 `DRAWIO_EXE` 环境变量；未配置时才查找 `drawio` / `draw.io` 命令。路径只用于本地进程启动，不进入探测结果、manifest 或日志。

当前内置布局器是 `diagramforge-semantic-v1`。官方 ELK 布局可通过外部 Draw.io 适配器接入；在完成固定版本和跨平台验证前，不把 ELK 宣称为内置能力。

## 跨软件交付

- Canvas → DiagramForge：只传递用户明确选择的文本、节点摘要和关系，不读取整张私有画布。
- DiagramForge → Photoshop / Illustrator：只交付确认后的 SVG 或 PDF 安全产物，不传递原始项目路径。
- `drawio.handoff.plan` 只返回文件名、媒体类型、大小和 SHA-256；它不启动目标软件，也不能替代目标板块自己的写入确认门。
- Photoshop / Illustrator → DiagramForge：只接收脱敏的状态、尺寸、数量和逻辑证据引用。

这些接口目前是受控交付边界，不代表自动打开或修改外部软件。
