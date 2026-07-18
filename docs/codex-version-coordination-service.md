# Codex 版本配置协同服务

`starbridge-version-coordinator` 是一个自包含 Codex 插件。它先根据客户的软件版本和 StarBridge v5-v9 代际生成安全路由计划，再把已通过能力探针的动作交给完整 StarBridge MCP。版本号只是协同信息，不是正版校验或版本白名单；协调器本身不读取客户素材、不扫描安装目录、不启动桌面软件，也不写配置或工程文件。

## 三分钟接入 Codex

先预览，不修改 Codex：

```powershell
powershell -ExecutionPolicy Bypass -File plugins\starbridge-version-coordinator\scripts\install.ps1 -DryRun
```

安装仓库 marketplace 和插件：

```powershell
powershell -ExecutionPolicy Bypass -File plugins\starbridge-version-coordinator\scripts\install.ps1
```

如果 `starbridge-local` 已经添加过：

```powershell
powershell -ExecutionPolicy Bypass -File plugins\starbridge-version-coordinator\scripts\install.ps1 -SkipMarketplaceAdd
```

安装后新建一个 Codex 任务，并说：

```text
请按 Photoshop 25.5、Illustrator 30.0 和 StarBridge v8 生成 safe 配置，并给出迁移到 v9 的最短步骤。
```

也可以在安装前直接验证自包含服务：

```powershell
python plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py self-test
python plugins\starbridge-version-coordinator\scripts\version_coordinator_mcp.py plan --software photoshop=25.5 --software illustrator=30.0 --generation v8
```

## 软件版本路由

| 软件 | 已知版本配置 | 未知或较低版本 | 默认安全边界 |
| --- | --- | --- | --- |
| Photoshop | 版本仅作协同信息；能力探针后选择 UXP / Node Proxy | COM 只读或 headless；先探针 | recipe 默认 dry-run |
| Illustrator | 版本仅作协同信息；能力探针后选择 UXP v2 / Node Proxy | headless SVG 或 COM 只读；先探针 | 桌面写入需 revision 与双确认 |
| AutoCAD / CAD | 版本只作为协同信息 | 始终保留 headless DXF | COM 可选；DXF 写入受控 |
| Blender | 版本只作为协同信息 | 先 CLI/环境探针 | 默认 plan-only |
| ComfyUI | 通过 loopback API 探针确认 | workflow validate-only | 不扫描模型目录 |
| CapCut / 剪映 | 版本只作为协同信息 | 草稿配置探针与人工打开 | 不读取私有草稿内容 |

Photoshop 和 Illustrator 的 UXP manifest 仍保留 `minVersion` 作为偏好提示，但不再把它当作阻断门槛；旧版、厂商后缀版和未知版都先进入只读能力探针。兼容性由探针和能力测试确认，不能把“探针通过”误写成桌面写入已验收。

## StarBridge v5-v9 迁移

| 代际 | 新增档位 | 迁移行为 |
| --- | --- | --- |
| v5 semantic | 几何意图、稳定选择器、紧凑编辑索引 | 作为所有后续版本的基础 |
| v6 refinement | 客户意图预校准、局部精修、patch 链 | 保留 v5 输出，生成新引用 |
| v7 paint | 块面合并、近似色压缩、基础色保护 | 不改未选路径和基础色 |
| v8 direction | 人工颜色组、对象命名、Illustrator 映射 | 不替客户猜配色和命名 |
| v9 illustrator | revision 门、回读、提交、回滚 | 真实写入仍需显式确认 |

迁移是增量计划，不会把旧产物原地重写，也不要求重新上传客户素材。

## Codex 中的三个工具

- `starbridge_config.catalog`：列出软件、别名、能力探针和 v5-v9 档位。
- `starbridge_config.plan`：生成软件版本、项目代际和安全模式的协同计划。
- `starbridge_config.migrate`：生成 v5-v9 之间的增量迁移步骤。

协调器是快速接入层；完整创意软件能力仍由 `python -m starbridge_mcp.mcp_server` 提供。项目级 Codex 配置可继续参考 `.codex/config.example.toml`。

## 普通客户硬规则

普通客户固定先调用像素级打印 / 精确重建技术，用 `exact_pixel_vector.py` 生成并验证无嵌入位图的 SVG 基线；其次才使用匠心矢量，或客户明确选择的智能 / 轻量矢量，生成更适合编辑的绘制型路径。客户交付不得使用 Illustrator Image Trace / 图像描摹，精确重建超限时也不得自动回退；此时必须停止并请客户选择缩小尺寸或调整交付目标。
