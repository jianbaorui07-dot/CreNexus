# 同类项目核心内容与 StarBridge 升级结论

更新时间：2026-06-12

这份说明只总结公开项目里值得借鉴的核心模式，不复制第三方源代码，也不把第三方私有假设带进 StarBridge。

## 同类项目的核心内容

### 1. ComfyUI 类项目

代表方向：

- `artokun/comfyui-mcp`
- `joenorton/comfyui-mcp-server`
- `IO-AtelierTech/comfyui-mcp`

共同核心：

- 把工作流当成一等对象，而不是只做一个 `txt2img` 按钮。
- 强调 `job status`、`asset identity`、`queue/history`、`workflow visualization`。
- 区分 `API workflow` 和 `UI workflow`，避免格式混用。
- 更成熟的项目会进一步做模型发现、节点发现、VRAM 监控和自动化工作流组合。

对 StarBridge 的启发：

- 应该保留当前 `validate first` 的保守路线。
- 但要把“输出边界、状态边界、证据边界”表达得更标准，而不是只靠文档口头约定。

### 2. Photoshop / Illustrator 类项目

代表方向：

- `loonghao/photoshop-python-api-mcp-server`
- `dcc-mcp/dcc-mcp-photoshop`
- `ie3jp/illustrator-mcp-server`
- `alisaitteke/photoshop-mcp`

共同核心：

- 会话层、文档层、图层层、导出层通常分开设计。
- 越成熟的项目，越不会把所有底层动作直接裸露给模型。
- 真正先进的路线正在从简单 COM/脚本调用，走向应用内桥接，例如 `UXP + WebSocket/HTTP adapter`。
- 安装方式更产品化，常见形态是 `npx`、扩展包、发布版二进制或远程 MCP 端点。

对 StarBridge 的启发：

- 公开仓库更适合保留“受控 recipe 层”，而不是扩大任意写工具。
- `session -> plan -> validate -> run -> evidence` 比“再加十几个底层命令”更稳。

### 3. CAD / 多桌面软件桥项目

代表方向：

- `puran-water/autocad-mcp`
- `AnCode666/multiCAD-mcp`

共同核心：

- 把 `headless fallback` 和 `real desktop control` 分层。
- 用统一 adapter 包不同 CAD 端。
- 先让没有桌面软件的环境也能做 plan/validate，再把真实写入作为受控分支。

对 StarBridge 的启发：

- 这条路线已经和 StarBridge 当前方向一致，应该继续强化，不要把离线 plan 和真实桌面控制混成一个口子。

### 4. 官方 MCP 新能力

代表方向：

- MCP `Roots`
- MCP `Elicitation`
- MCP `Sampling`

共同核心：

- `Roots` 负责正式表达文件系统边界。
- `Elicitation` 负责正式表达需要用户确认或补充信息的交互。
- `Sampling` 负责让 server 在不自带模型 key 的情况下，向 client 请求模型推理。

对 StarBridge 的启发：

- 你的仓库最该跟进的不是“更多工具”，而是“更标准地表达安全边界”。

## 这次落地到 StarBridge 的升级

### 1. 新增 `starbridge.safe_roots`

现在可以直接返回：

- 哪些目录是公开只读根
- 哪些目录是本地可写 sandbox / ignored output 根
- 哪些根适合映射为 MCP roots

这让 StarBridge 的“只能写哪些目录”第一次变成了正式能力，而不只是 README 里的约定。

### 2. 补齐 Photoshop recipe 层的最小可调用面

新增：

- `photoshop.recipe_list`
- `photoshop.recipe_plan`
- `photoshop.recipe_validate`
- `photoshop.recipe_run`
- `photoshop.recipe_debug`

这一层延续的是“先计划、先校验、默认 dry-run、显式确认真实写入”的路线。

### 3. 能力注册表和 MCP tool 元数据更完整

这次补齐了：

- `current_status`
- `bridge_categories`
- tool annotations 里的风险与确认元数据

这样后续无论是给 Codex、Claude 还是别的 MCP client，看起来都会更像一个有边界的工具系统，而不是零散脚本集合。

## 不建议现在直接照搬的内容

- 不建议引入自动下载模型、自动装节点、自动扫本机工程目录。
- 不建议把任意脚本执行、任意 PSD/AI/DWG 打开做成公开能力。
- 不建议为了“看起来先进”把项目改成云端优先；你这个仓库目前最有价值的点就是本机软件接入的公开安全方法。
