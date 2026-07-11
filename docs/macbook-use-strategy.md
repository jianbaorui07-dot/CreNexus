# StarBridge MacBook 使用策略

## 定位

StarBridge 当前是 Windows-first，但其 MCP stdio、Recipe Plan、CreativeTransaction、EvidenceManifest、ComfyUI HTTP、Blender 计划和 Adobe UXP / Node Proxy 的大部分协议层可以在 macOS 上运行。

MacBook 策略不是模拟 Windows，而是将能力分成三条通道：

1. **Mac 本地通道**：MCP、Recipe、安全校验、ComfyUI、Blender、UXP。
2. **GUI 观察通道**：由 Computer Use 观察 Photoshop、Illustrator、Blender 等桌面软件，再用 MCP 验证结果。
3. **Windows 执行节点**：AutoCAD COM、Windows-only PowerShell 和其他仅 Windows 插件留在受控 Windows 主机。

MacBook 不应自动打开客户工程、扫描私有目录或把素材上传到远程服务。

## 建议硬件和运行模式

| MacBook 配置 | 建议用途 | 不建议 |
| --- | --- | --- |
| Apple silicon、16 GB 统一内存 | MCP、文档、轻量 Photoshop / Illustrator、小型 Blender | 大型本地生成模型和复杂 3D 渲染 |
| Apple silicon、24–36 GB | 常规创意工作台、ComfyUI 中等 workflow、Blender 预览 | 长时间满负载且无散热管理 |
| Apple silicon、48 GB 及以上 | 较大 ComfyUI workflow、多软件并行、较大场景 | 将统一内存当作独立显存对等使用 |
| Intel Mac | MCP 协议开发和只读检查 | 作为新的本地 AI 生产主机 |

对无风扇的 MacBook Air，优先采用短任务和远程 GPU 通道；对 MacBook Pro，可本地运行中等规模的 ComfyUI / Blender 任务，但仍应设置超时、步数和资源上限。

## 安装基线

安装前由用户手动确认 Xcode Command Line Tools、Python 3.11+ 和 Node.js LTS 的来源。不将 Homebrew、管理员密码或系统设置修改放入自动化脚本。

```bash
git clone https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software.git
cd Codex-Integration-with-Creative-Industry-Software

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
npm install
```

基础验证：

```bash
python -m unittest discover -s tests
python scripts/security_check.py
python examples/bridge_status.py --json --redact-paths --soft-exit
```

macOS 上使用 `/` 路径和 `python3` / venv，不直接复制 README 中的 `npm.cmd`、PowerShell、COM 或 Windows 安装路径命令。

## 软件桥策略

| 软件桥 | MacBook 策略 | 默认风险 | 执行边界 |
| --- | --- | --- | --- |
| StarBridge MCP | 本地原生运行 stdio server | `L0–L2` | 优先只读和 dry-run |
| ComfyUI | 通过 localhost HTTP 连接用户明确启动的 ComfyUI | `L1–L3` | 提交 queue 前必须明示确认；不扫描 checkpoint 目录 |
| Blender | 优先 scene plan、reference plan 和受限制脚本 | `L1–L3` | 禁止任意 Python；输出仅到 sandbox / ignored output |
| Photoshop | 优先 UXP + Node Proxy，GUI 只用于观察和确认 | `L1–L3` | 不使用 Windows COM；BatchPlay 只允许 typed allowlist |
| Illustrator | 优先 UXP / 受审查本地插件；未接通时只返回 plan | `L1–L3` | 导出和追踪必须确认并限定输出目录 |
| AutoCAD / DXF | DXF schema、validate、dry-run 可本地运行；AutoCAD COM 留在 Windows | `L1–L3` | Mac 不声称支持 `AutoCAD.Application` COM |
| CapCut | 只做用户显式传入的脱敏草稿摘要研究 | `L1–L3` | 不扫描草稿目录、不读账号状态、不自动导出 |
| Unreal Engine | 视为试验性 plan / evidence 通道 | `L2–L3` | 不承诺 Windows 插件或远程控制兼容 |

## Apple silicon 和依赖策略

- Python、Node.js、Blender 和本地插件尽量统一使用 `arm64` 版本。
- 不在同一进程链中混用 `arm64` 和 `x86_64` 依赖。
- 只有明确的第三方组件必须使用 Intel 版本时，才由用户手动启用 Rosetta 2。
- 记录架构、Python 版本和 bridge 可用性，但 Evidence 中不记录用户名和绝对安装路径。

只读检查：

```bash
uname -m
python -c "import platform; print(platform.machine(), platform.python_version())"
node -p "process.arch"
```

## 文件、权限和隐私

macOS 的 Desktop、Documents、Downloads、Photos Library 可能受 TCC 隐私权限管理。StarBridge 不应为了通过探针而要求 Full Disk Access。

建议工作区：

```text
~/StarBridgeWorkspace/
├── inbox/       # 用户显式放入的输入
├── sandbox/     # 可丢弃预览
├── output/      # 已确认输出
└── evidence/    # 脱敏审计记录
```

规则：

- safe roots 必须由用户显式配置，不默认扫描 `~/Documents` 或 `~/Library`。
- 不跟随指向 safe roots 外部的符号链接。
- Evidence 仅保存相对路径、basename、hash 和质量结果。
- 密钥优先由 macOS Keychain 或运行时环境注入，不写入 Recipe、Evidence 或 Git。
- 不自动修改 Gatekeeper、SIP、防火墙、登录项或辅助功能权限。

## Windows 远程执行节点

AutoCAD COM 等 Windows-only 能力应作为独立执行节点，而不是让 Mac 端发送任意命令。

```text
Mac Planner
  -> 脱敏 CreativeTransaction
  -> 用户确认
  -> Windows Executor allowlist
  -> 脱敏 EvidenceManifest
  -> Mac Visual Review
```

远程节点必须：

- 只接受签名 Recipe ID 和结构化参数，不接受 shell 文本。
- 使用短期凭据和明确 allowlist。
- 在 Windows 端再次检查 safe roots 和确认状态。
- 不回传原始 PSD、DWG、素材或用户绝对路径。
- 网络中断时进入 `failed` 或 `repair_needed`，不自动重复写入。

## GPT-5.6 模型使用策略

Recipe 只声明能力层，不绑定具体模型 ID：

| 阶段 | 能力别名 | 任务 |
| --- | --- | --- |
| 跨软件规划 | `frontier` | 意图分解、风险评估、Recipe 设计 |
| 常规参数填充 | `balanced` | schema 参数、工具路由 |
| 轮询和日志摘要 | `fast` | JobStatus、Evidence 归档 |
| 视觉结果复核 | `frontier` | 构图、裁切、溢出和意外变更检查 |

在电池供电、高温或低带宽状态下，优先 `balanced` / `fast` 和短任务；不因设备性能不足而放宽安全门。

## 标准使用流程

1. 将必要输入手动复制到已配置 `inbox` or sandbox，不授予整盘权限。
2. 运行脱敏 `status` 和 safe roots 检查。
3. 生成 `CreativeTransaction`，先审查风险等级、输出和审批点。
4. 运行 Recipe dry-run，不启动写入。
5. 用户确认后只执行批准的单个事务。
6. 使用 MCP 结构化结果加 GUI 截图进行双重验证。
7. 只保存脱敏 Evidence；失败时丢弃 sandbox 输出，不覆盖原工程。

## 发布前验收

Mac 支持只能按实际验证结果声明：

- Python 单元测试在 macOS arm64 CI 通过。
- MCP stdio initialize / tools/list / tools/call 通过。
- 安全扫描不出现真实用户主目录；报告中统一脱敏为 `<USER_HOME>`。
- ComfyUI / Blender 缺失时 soft-exit，不阻断基础 CI。
- Windows-only 能力返回 `unsupported_platform` 或 `remote_executor_required`，不伪装成可执行。
- Photoshop / Illustrator 只在经审查的本地 UXP 实测后标记为 experimental，否则保持 planned。

在完成上述验收前，对外表述应使用 **macOS strategy / protocol-compatible**，不使用 **full macOS support**。
