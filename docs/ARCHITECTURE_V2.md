# StarBridge 工作流架构 v2

状态：已确认，按小步兼容迁移实施。现有 CLI、MCP、backend、四种矢量化引擎、Tauri/React、Python sidecar 和全部软件桥继续保留。

## 分层

```text
Desktop / CLI / MCP
→ 通用 Project/Job API 与旧 VectorJob 兼容层
→ Workflow Engine、状态机与确认门
→ 统一 Adapter 接口
→ 现有矢量化、ComfyUI、Adobe、Blender、AutoCAD、CapCut 实现
→ Project / Job / Artifact / Evidence / Delivery 持久化
```

## 领域模型

`Project` 包含 `projectId`、`projectName`、`workflowId`、`description`、`sourceAssets`、`currentJob`、`jobHistory`、`artifacts`、`qualityReports` 和 `evidence`。

`CreativeJob` 包含 `jobId`、`projectId`、`workflowId`、`status`、`currentStep`、`progress`、时间字段、`artifacts`、`warnings`、结构化 `error` 和可选 `evidenceId`。配套模型为 `WorkflowPlan`、`WorkflowStep`、`Artifact`、`QualityMetric`、`JobError`、`EvidenceManifest` 引用和 `JobHistoryEvent`。

状态机只允许：

```text
queued → running → needs_user → running
queued/running/needs_user → cancelled
running → completed/failed
```

`completed / failed / cancelled` 为不可逆终态。

## 应用数据

```text
%LOCALAPPDATA%/StarBridge/
├─ projects/<projectId>/project.json
├─ jobs/<jobId>/job.json + events.jsonl
├─ artifacts/<projectId>/<jobId>/
├─ evidence/<evidenceId>/manifest.json
└─ deliveries/<projectId>/<deliveryId>/
```

现有 `data/history/logs/cache/diagnostics` 继续保留。写入使用临时文件、flush、fsync 和原子替换；事件历史只追加。导入源文件必须由用户明确选择并确认复制到受控目录，证据只保存 ID、basename、SHA-256 和受控相对路径。

## 工作流步骤与确认

每个步骤包含 `step_id / adapter / input / output / validation / requires_confirmation / optional / retry_policy / rollback_policy`。确认凭据绑定 `jobId + workflowId + stepId + planHash + revision + safeRoot`，单次使用并具有期限。

Adapter 统一提供 `probe / plan / validate / execute / cancel / collect_artifacts / collect_evidence`。Adapter 不直接控制全局任务状态；软件不可用时返回脱敏、结构化 soft-exit。

## 兼容策略

- `/api/vectorization/*`、VectorJob、旧 Tauri commands、CLI 和 MCP tools 保持可用。
- VectorJob 是 CreativeJob 的兼容投影；新执行由 Workflow Engine 调度。
- 旧历史保持只读兼容，不删除、不覆盖。
- EvidenceManifest 的仓库默认输出继续服务 CLI/tests；桌面端注入应用数据 EvidenceStore。

## 实施顺序

1. 修复 bootstrap、CI、安全扫描和产品事实。
2. 建立 Project、CreativeJob、持久化和状态机。
3. 包装 `vector-delivery-v1`，保持旧矢量 API。
4. 增加项目、工作流、任务详情和交付页面。
5. 接入 `comfyui-generation-v1`。
6. 再实现有限 Photoshop、Illustrator 和统一交付打包。
7. 通用任务稳定后开发 Pro 批量；Blender、CAD 和视频完整工作流最后实施。
