# StarBridge 产品化审计

> 当前审计基线：`origin/main` 提交 `fad9268`，审计日期 2026-07-18。早期基线 `86371fd` 的审计结论已过时，不再作为当前产品事实。

## 当前结论

仓库已经拥有 Python CLI、StarBridge MCP、Tool Registry、safe roots、路径脱敏、确认门、EvidenceManifest、JobStatus、四种矢量化引擎、Tauri 2 + React 桌面端、Python sidecar、NSIS/更新器代码和多种创意软件桥。架构升级必须保留这些能力，通过兼容层和 Workflow Engine 逐步迁移，不能推倒重写。

审计中前四项缺口已在 `codex/workflow-foundation` 实施，当前剩余发布与第三方软件验收缺口为：

1. 安装器和更新器没有签名、公开 Release、干净 Windows、完整 Defender、SmartScreen 和真实升级证据。
2. Adobe、Blender、AutoCAD、ComfyUI、CapCut 的代码、协议或 mock 证据不能宣传为当前真实软件已连接。
3. `vector-delivery-v1` 尚未生成经过真实 Illustrator 验收的 AI 副本；交付中心只列出实际存在的格式。
4. `comfyui-generation-v1` 已通过模拟回环集成测试，但尚未在用户授权的本机 ComfyUI 上验收。
5. `photoshop-production-v1` 已通过模拟 UXP 代理闭环，但真实 Photoshop 导入、调整层、主体选择和 PNG/JPEG/PSD 导出仍未验收。

已完成的基础包括 bootstrap/CI/安全扫描修复、统一产品事实、Project/CreativeJob/Workflow Engine 持久化、旧 VectorJob 兼容、三个 v1 工作流和桌面项目/任务/交付主路径。

## 当前事实入口

- 产品状态与 Community/Pro 边界：[PRODUCT_FACTS.md](PRODUCT_FACTS.md)
- 机器可读 manifest：`product/product-manifest.json`
- 能力状态 schema：`product/capability-status.schema.json`
- 新架构和兼容策略：[ARCHITECTURE_V2.md](ARCHITECTURE_V2.md)
- 实施顺序：根目录 `ROADMAP.md`

## 已确认实施方向

```text
保留核心
→ 修复可信基线
→ 增加 Project / CreativeJob 持久化
→ 建立 Workflow Engine 和统一 Adapter
→ 包装 vector-delivery-v1
→ 迁移桌面项目/任务/交付页面
→ 接入 comfyui-generation-v1
→ 有限 Photoshop / Illustrator
→ Pro 批量后置
```

## 安全边界

- local-first，默认只读、plan 或 dry-run。
- 写入必须明确确认，并限制在 safe roots 或应用数据目录。
- 不递归扫描未授权目录，不覆盖或删除源文件。
- 不保存 token、Cookie、OAuth 缓存、账号状态、客户素材或真实绝对路径。
- 软件缺失时结构化 soft-exit；未经真实授权软件验收不得显示 `connected` 或 `stable` 写入。

## 验证基线

每个实施阶段至少运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Profile auto
npm.cmd test
npm.cmd run preflight
npm.cmd run desktop:test
npm.cmd run desktop:build
npm.cmd run desktop:sidecar:test
python scripts\security_check.py
python scripts\check_product_facts.py
python examples\bridge_status.py --json --redact-paths --soft-exit
```

涉及真实软件时必须先 `probe` 和 `plan`，再由用户明确确认执行。未运行项和原因必须随阶段结果记录。
