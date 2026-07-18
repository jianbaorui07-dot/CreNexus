---
name: starbridge-version-coordination
description: Configure StarBridge for different Photoshop, Illustrator, AutoCAD, Blender, ComfyUI, CapCut/Jianying, or StarBridge v5-v9 versions in Codex. Use for compatibility planning, safe route selection, quick Codex setup, or migration from v5-v8 to v9. Do not use this skill to claim desktop automation passed or to write customer files.
---

# StarBridge 版本配置协同

先把“客户本机软件版本”和“StarBridge 项目代际”分开记录。软件版本使用 `software_versions`，项目代际使用 `starbridge_generation`。

## 工作流

1. 软件或别名不清楚时，先调用 `starbridge_config.catalog`。
2. 调用 `starbridge_config.plan`：
   - `software_versions` 只填写短版本号，例如 `25.5` 或 `30.0.1`；不要传安装路径。
   - 未提供版本时保留 `unknown`，让计划选择只读能力探针；不要猜版本。manifest 的 `minVersion` 只是偏好提示，不是版本白名单或授权检查。
   - 默认 `safety_mode=safe`。
3. 如果客户仍在 v5-v8，调用 `starbridge_config.migrate` 生成增量迁移步骤；保留旧产物和旧引用。
4. 先执行计划返回的 `probe_tool`。只有完整 StarBridge MCP 已连接且探针通过，才继续使用 `full_mcp_tools`。
5. 本协调器只生成计划。真实写入仍需完整 StarBridge MCP、显式确认和 sandbox/output 边界。

## 客户默认顺序

1. 先用 `exact_pixel_vector.py` 做像素级打印 / 精确重建，验证无嵌入位图的 SVG 基线。
2. 再按客户目标使用匠心矢量，或客户明确选择的智能 / 轻量矢量，生成绘制型路径。
3. 客户交付不得使用 Illustrator Image Trace / 图像描摹；精确重建超限时停止，不自动回退。

## 路由规则

- Photoshop 的版本只用于协同记录；所有版本先走只读能力探针，再选择 UXP、Node Proxy 或 COM/headless 回退。
- Illustrator 的版本只用于协同记录；所有版本先走只读能力探针，再选择 UXP、Node Proxy 或 headless SVG/COM 回退。
- AutoCAD 默认使用 headless DXF；COM 只是可选增强。
- Blender 默认只生成计划并做 CLI 探针，不把已记录版本当成已验证兼容。
- ComfyUI 先探测 loopback API；不扫描模型目录。
- CapCut/剪映只做可执行文件/草稿配置探针与脱敏摘要，打开和导出保持人工确认。

## 安全边界

不要把 PSD、AI、DWG、`.blend`、剪映草稿、模型、token、账号、安装路径或客户素材传给协调工具。版本计划不得描述为真实桌面验收结果。
