# StarBridge：精确像素矢量重建 + Codex Skill + MCP

[![CI](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml/badge.svg)](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml)
![Windows first](https://img.shields.io/badge/Windows-first-2563eb)
![MCP stdio](https://img.shields.io/badge/MCP-stdio-16a34a)
![Local first](https://img.shields.io/badge/local--first-safe-0f766e)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

StarBridge 是以**图片精确转 SVG / Illustrator AI**为主推能力的本地创意软件开源接入层。它把 **Codex Skill** 的任务路由、**StarBridge MCP** 的结构化工具，以及 **Adobe UXP / Node Proxy** 的桌面软件通道组合成一套可审计的工作流；ComfyUI、Photoshop、CAD / AutoCAD、Blender 和 CapCut / 剪映等桥仍完整保留。

当前默认图片转矢量路线不使用 Illustrator Image Trace。它把用户明确授权的单张 PNG / JPEG 按原始 RGBA 像素网格重建为矩形复合路径，验证 SVG 中没有嵌入位图、脚本或外链，再交给 Illustrator 存储为 `.ai`。颜色不量化、像素不缩放，复杂度会如实反映在路径数量和写入时间上。

```mermaid
flowchart LR
  A["用户授权的单张 PNG / JPEG"] --> B["读取原始 RGBA 像素"]
  B --> C["连续同色像素合并为矩形"]
  C --> D["按 paint 合并复合 path"]
  D --> E["验证 SVG 无位图 / 脚本 / 外链"]
  E --> F["Illustrator 打开并存储为 AI"]
  F --> G["核对文件与脱敏证据"]
```

项目坚持 local-first：默认只读或 `dry-run`，真实写入必须显式确认并限制在安全输出目录；仓库不保存客户素材、PSD / AI / DWG 私有工程、账号状态、模型文件、token 或本机路径。

## 当前状态：v0.1-alpha

| 状态 | 已覆盖能力 | 证据边界 |
| --- | --- | --- |
| stable（稳定） | MCP stdio、工具注册、resources / prompts、状态探针、路径脱敏、operation context、ComfyUI 队列/进度/任务快照与工作流验证；AutoCAD/DXF plan validate / dry-run / guarded write | Windows 与 Ubuntu CI 验证结构、schema、安全边界和 soft-exit |
| primary（主推） | 精确 RGBA 像素→矩形复合路径→已验证 SVG→Illustrator AI 交付 | 不使用 Image Trace、不嵌入位图、不量化颜色；只读单张明确输入，输出留在忽略 sandbox；桌面 AI 写入需要明确请求 |
| experimental（其他 Adobe 协议） | Photoshop / Illustrator 规划、预检、受控执行接口；彩色矢量化 plan / validate / compare / repair_plan / execute；旧量化 SVG fallback | 兼容与研究用途；默认不作为普通图片转矢量入口；compare 只读取两个明确授权文件 |
| UXP 安全执行已实现 | Photoshop `executeAsModal` 有界排队、取消状态、history commit / rollback、临时文档自动关闭 | 已通过 Node 模拟与协议测试；仍需已授权 Photoshop 桌面实测 |
| planned（仍在推进） | repair plan → Illustrator execute → compare 的显式确认闭环、Adobe 桌面端端到端验收、Blender 确认渲染、CapCut 草稿骨架 | 未经本地运行证据，不宣称真实桌面控制已验证 |
| not implemented（不实现） | 自动登录、绕过授权、递归扫描私有目录、无确认写入真实软件、上传客户工程或商业素材 | 安全硬边界 |

Photoshop, Illustrator, Blender, and CapCut write flows are experimental or planned unless a reviewed local run proves otherwise.

完整状态见 [精确像素矢量重建](docs/exact-pixel-vectorization.md)、[能力矩阵](docs/CAPABILITY_MATRIX.md)、[彩色矢量化协议](docs/color-faithful-vectorization.md) 和 [v0.1-alpha 发布说明](docs/RELEASE_V0_1_ALPHA.md)。

## 主推：精确像素矢量重建

目标是在源像素网格上确定性地保留 RGBA 值与位置，同时产出不含嵌入位图的可编辑矢量文件。详细写入过程和本机证据见[精确像素矢量重建文档](docs/exact-pixel-vectorization.md)。

| 阶段 | 作用 | 默认行为 |
| --- | --- | --- |
| 输入 | 一张明确授权的 PNG / JPEG | 不扫描目录、不上传云端 |
| 重建 | 连续同色像素→矩形子路径；按 RGBA paint 合并复合 path | 不缩放、不模糊、不量化颜色 |
| 验证 | 复读 SVG 尺寸、路径、颜色、透明度和 hash | 拒绝位图、脚本、外链和越界坐标 |
| AI 交付 | Illustrator 打开 SVG 并“存储为” `.ai` | 不使用图像描摹；桌面写入需明确请求 |
| 大文件写入 | 监控 Illustrator 响应和 CPU 进展，完成后核对文件 | 不因短暂未出现文件而过早中断 |

超过 4,000,000 像素、2,000,000 个矩形子路径或 64 MiB SVG verifier 限制时，流程停止并交还用户，不自动回退到 Image Trace。

## 5 分钟开始

环境：Windows 优先、Python 3.10+；仅在运行 UXP 本地代理或前端示例时需要 Node.js。

```powershell
git clone https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software.git
cd Codex-Integration-with-Creative-Industry-Software

python -m pip install --upgrade pip
pip install -e ".[dev]"
```

先运行不依赖桌面软件的安全检查：

```powershell
python examples\bridge_status.py --json --redact-paths --soft-exit
python -m starbridge_mcp.server tools --json --safe-only
python scripts\security_check.py
python -m unittest discover -s tests
```

安装 Node.js 后也可使用快捷命令：

```powershell
npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
npm.cmd run preflight
npm.cmd test
```

PowerShell 如果拦截 `npm.ps1`，请使用 `npm.cmd`。

## 图片直接转矢量图

| 路线 | 适用场景 | 当前证据 |
| --- | --- | --- |
| **精确像素矢量重建（默认）** | 普通 PNG/JPEG→逐像素矩形复合路径→SVG→Illustrator AI | 确定性输出、原始 RGBA paint、无嵌入位图；736×1314 本机样例成功生成 742,922 个子路径 AI |
| 旧量化 SVG 实验 | 扁平插画、图标和色块稿的低复杂度候选 | 保留兼容命令、CI 复读 SVG；不作为默认图片转矢量入口 |
| 原生 Image Trace 协议 | 研究、兼容和既有 MCP schema | 代码仍保留；普通图片转矢量工作流禁止自动选择 |

主推命令：

```powershell
python -m pip install -e ".[illustrator-vector]"
npm.cmd run illustrator:vectorize:offline -- --input "<input.png>" --reference-id "reference"
```

默认输出写入已被 Git 忽略的 `examples/output/illustrator/exact-pixel/<reference-id>/`。脚本记录脱敏输入 hash、画布、像素数、path 数、矩形子路径数、paint 数、SVG bytes 与 hash；不返回源文件名或绝对路径。

旧量化命令仍可用于兼容实验：

```powershell
npm.cmd run illustrator:vectorize:legacy-quantized -- --input "<input.png>" --commit-preset flat_16
```

复杂照片会生成很大的 SVG / AI；这是保留源像素复杂度的结果。源图与生成结果不能提交到仓库。

## 架构

```mermaid
flowchart LR
  A["Codex / AI 客户端"] --> B["Codex Skills"]
  B --> C["StarBridge MCP stdio"]
  C --> D["Tool Registry / Resources / Prompts"]
  D --> E["安全层：dry-run / redact / confirm / sandbox"]
  E --> F["Adobe UXP / Node Proxy"]
  E --> G["ComfyUI / CAD / Blender 探针"]
  F --> H["Photoshop / Illustrator"]
```

- Skill 负责选择工作流、路由和验证顺序，不保存素材。
- MCP 负责稳定、结构化、可审计的工具调用与证据摘要。
- UXP / Node Proxy 负责受控桌面通道，不开放任意脚本执行。
- Photoshop、Illustrator、AutoCAD、Blender 等专业软件仍负责真实生产。

## 能力入口

| 目标 | 文档 | 验证入口 |
| --- | --- | --- |
| 项目定位 | [Skill / MCP / UXP 定位](docs/skill-mcp-uxp-positioning.md) | `python scripts\starbridge_preflight.py --markdown` |
| Photoshop | [Photoshop 接入](docs/03-codex-photoshop.md) / [UXP modal 安全协议](docs/photoshop-uxp-modal-envelope.md) | `npm.cmd run photoshop:diagnose` |
| Illustrator | [Illustrator 接入](docs/05-codex-illustrator.md) | `npm.cmd run illustrator:preflight:plan` |
| 精确图片转 SVG / AI | [精确像素矢量重建](docs/exact-pixel-vectorization.md) | `npm.cmd run illustrator:vectorize:offline -- --input "<input.png>" --reference-id "reference"` |
| 其他彩色矢量协议 | [参考图彩色矢量化协议](docs/color-faithful-vectorization.md) | MCP `illustrator.color_vectorize_compare` |
| ComfyUI | [ComfyUI 接入](docs/02-codex-comfyui.md) | `python examples\comfy_bridge\comfy_probe.py` |
| CAD / AutoCAD | [CAD 接入](docs/01-codex-cad.md) | `python scripts\test_autocad_mcp.py` |
| Blender | [Blender 接入](docs/04-codex-blender.md) | `npm.cmd run blender:scene:plan` |
| CapCut / 剪映 | [CapCut 接入](docs/06-codex-jianying.md) | `npm.cmd run capcut:draft:structure` |
| MCP 客户端配置 | [本地 MCP 配置](docs/local-mcp-setup.md) | `python -m starbridge_mcp.server tools --json --safe-only` |
| 中文导航 | [中文用途索引](docs/中文用途索引.md) | 按软件和目标查找入口 |

### 中文阅读指南与仓库区域标注

| 中文区域 | 对应能力 |
| --- | --- |
| 图像生成区 | ComfyUI workflow 校验、队列监控、模板和任务生命周期摘要 |
| 工程制图区 | CAD / AutoCAD plan、DXF dry-run 与受控写入 |
| AI 矢量文件桥 | 主推精确像素矢量重建；另保留 Illustrator 规划、比较、修复协议和旧量化 SVG 实验 |
| 图像编辑区 | Photoshop UXP、Node Proxy、modal 回滚与 sandbox demo |
| 视频草稿区 | CapCut / 剪映只读探针；未配置时报告“剪映可执行文件”状态 |

## 仓库结构

```text
.codex/skills/starbridge-*   Codex Skill 入口、安全边界与验证命令
starbridge_mcp/              MCP server、tool registry 与安全层
examples/                    参数化、默认安全的公开桥接示例
uxp/                         Adobe UXP 插件原型
node_proxy/                  UXP / MCP 本地代理示例
cad-mcp-autocad/             AutoCAD MCP 子项目
scripts/                     CAD 自动化与仓库验证脚本
tests/                       离线测试与安全边界测试
docs/                        接入协议、能力矩阵与中文索引
```

## 安全模型

新增或调整 MCP tool 必须先有文档、schema 和测试，并满足：

- 默认只生成计划或执行只读检查；
- `safe-only` 可过滤高风险能力；
- 输出经过路径脱敏和 sanitizer；
- 失败使用 soft-exit 或结构化 error；
- 写入必须显式确认，并限制到 sandbox / output；
- 不递归扫描私有目录，不读取未明确传入的素材或工程。

本仓库不接收 PSD、AI、DWG、`.blend`、CapCut 草稿、客户素材、模型权重、授权文件、token、Cookie、OAuth 缓存、真实安装路径或生成结果。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## 开发与验证

```powershell
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests
python scripts/security_check.py
python scripts/collect_bridge_status.py --json
python examples/bridge_status.py --json --redact-paths --soft-exit
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
python scripts\starbridge_preflight.py --markdown
python scripts\starbridge_preflight.py --write-report --soft-exit
npm.cmd test
```

桌面软件命令需要 Windows、本机已安装且已授权的软件。Ubuntu CI 只证明跨平台逻辑、schema、安全边界和 soft-exit 通过，不代表真实软件控制已经验收。

贡献规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。PR 必须说明变更范围、已运行验证、未运行原因和私有资产泄漏风险。

## 发布资料

- [Adobe 安全演示索引](docs/adobe-demo-gallery.md)
- [Adobe 演示 smoke test](docs/adobe-demo-smoke-test.md)
- [版本记录](CHANGELOG.md)
- [路线图](ROADMAP.md)
- [发布说明草稿](RELEASE_NOTES_DRAFT.md)

## English

StarBridge is a Windows-first, local-first integration layer whose primary workflow reconstructs an authorized PNG/JPEG pixel grid as grouped RGBA rectangle paths, verifies a raster-free SVG, and hands it to Illustrator for Save As AI without Image Trace. The repository also retains guarded Adobe protocols, legacy quantized SVG research, ComfyUI, CAD/AutoCAD, Blender, CapCut/Jianying, MCP stdio, UXP, and local proxy bridges. Public examples default to read-only checks or safe ignored outputs; desktop writes require explicit confirmation.

## License

[MIT](LICENSE)
