# DiagramForge safe bridge

DiagramForge 是 CreNexus 的结构化绘图板块，和自由批注型 Canvas 分开。它用确定性 Python 编译器生成原生 `.drawio`、内嵌可编辑 XML 的 SVG 预览和结构 manifest；不要求浏览器、Draw.io Desktop 或外部 MCP 才能完成基础生成与验证。

只读入口：

```powershell
python examples/drawio_bridge/cli.py probe
python examples/drawio_bridge/cli.py capabilities
python examples/drawio_bridge/cli.py plan --recipe research-framework-v1
python examples/drawio_bridge/cli.py batch --recipe system-architecture-v1 --count 3
```

写入始终要求显式确认，并限定在 `.gitignore` 覆盖的安全输出目录：

```powershell
python examples/drawio_bridge/cli.py demo --confirm-write
python examples/drawio_bridge/cli.py validate examples/output/diagramforge/research-framework.drawio
```

`patch` 使用稳定元素 ID，只更新指定元素。工具会比较修改前后的逐元素哈希；任何无关元素发生变化都会拒绝提交事务。

`handoff` 只为 Canvas、Photoshop 或 Illustrator 生成脱敏、哈希绑定的下游导入计划；它不启动目标软件，也不绕过目标桥自己的确认门。

当前可验证的 headless 交付是 `.drawio`、`.drawio.svg` 和 manifest。PDF 仅在探测到 Draw.io Desktop CLI 后开放；实时画布可通过官方 `@drawio/mcp` 或兼容 Live MCP 作为可选外部适配器接入，核心编译器不依赖外部服务。
