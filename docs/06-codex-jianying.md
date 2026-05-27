# 6. Codex 接入剪映 / CapCut

调研日期：2026-05-23

这份文档记录 Codex 接入剪映专业版 / CapCut Desktop 的初步路线。当前状态是 `research`：仓库只有调研、`bridge.json` manifest、环境探测和本地草稿桥方向，没有稳定的桌面自动化闭环。

公开仓库不提交本机草稿、素材路径、导出视频、账号信息、会员状态或剪映 / CapCut 缓存。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| manifest | `examples/capcut_jianying_bridge/bridge.json` | 声明 research 状态、入口、支持任务和安全说明 |
| 环境探测 | `examples/capcut_jianying_bridge/probe.py` | 检查剪映 / CapCut 可执行文件和草稿目录环境变量 |
| 总状态探测 | `examples/bridge_status.py` | 检查 `JIANYING_EXE`、`CAPCUT_EXE`、草稿目录配置 |
| 路线文档 | 本文档 | 说明草稿桥、模板替换和 MCP 封装方向 |

## 需要本机安装什么

- 剪映专业版或 CapCut desktop。
- 用户手动确认软件可正常打开。
- 用户手动确认草稿目录。
- 如果后续验证开源草稿库，需要在本机独立安装和验证许可。

真实路径只放本机环境变量或本地 `.env`：

```powershell
$env:JIANYING_EXE="<path-to-jianying.exe>"
$env:JIANYING_DRAFTS_DIR="<path-to-jianying-drafts>"
$env:CAPCUT_EXE="<path-to-capcut.exe>"
$env:CAPCUT_DRAFTS_DIR="<path-to-capcut-drafts>"
```

## 验证命令

```powershell
npm.cmd run status:probe:json
```

直接运行：

```powershell
python examples\capcut_jianying_bridge\probe.py
python examples\bridge_status.py --json
```

这些命令只做环境和目录线索探测，不会写入草稿，不会导出视频，也不会自动控制账号。

## 调研结论

- 推荐路线是 **本地草稿桥**：Codex 生成或检查剪映 / CapCut 可打开的本地草稿，用户在软件里打开、确认和导出。
- 当前不把方向放在网页登录、云端接口抓包、绕过会员限制、自动点击 UI 或控制账号功能上。
- 当前没有在本仓库内验证出稳定官方桌面 API，因此不能把“自动控制剪映 / CapCut 桌面版”写成已完成能力。
- 可以研究 `pyJianYingDraft`、`pyCapCut`、本地 FastAPI / MCP 包装等方向，但进入仓库前必须先验证许可、依赖、草稿兼容性和隐私边界。

## 推荐路线

### 1. 只读状态检查

先只读取环境变量，不扫描全盘：

```powershell
$env:JIANYING_DRAFTS_DIR="<path-to-jianying-drafts>"
$env:CAPCUT_DRAFTS_DIR="<path-to-capcut-drafts>"
```

探针只做这些事：

- 检查草稿目录是否存在。
- 统计公开安全的摘要信息，不输出真实素材路径。
- 检查候选依赖是否安装。
- 输出状态和下一步建议。

### 2. 生成公开安全测试草稿

第二步再考虑最小草稿：

- 使用程序生成的纯色图、测试文字或本地临时音频占位，不使用用户私有素材。
- 草稿名称使用公开安全名称，例如 `codex_jianying_probe`。
- 输出到用户通过环境变量指定的草稿目录，或输出到 `output/` 让用户手动复制。
- 生成后由用户在剪映 / CapCut 里打开检查，导出仍由用户手动处理。

### 3. 模板草稿替换

复杂字体、花字、转场、滤镜、字幕样式和贴纸最好先由用户手动做成模板。Codex 只替换可参数化内容：

| 替换对象 | Codex 可做的事 |
| --- | --- |
| 文本 | 替换标题、口播字幕、商品卖点、章节标题 |
| 视频 | 按片段名或模板槽位替换素材 |
| 图片 | 替换封面、产品图、背景图 |
| 音频 | 替换 BGM、旁白、音效 |
| 字幕 | 导入或更新 `.srt`，保留模板样式 |

## 不能做什么

- 不能声称已经有稳定官方桌面 API。
- 不能提交剪映 / CapCut 草稿、`draft_content.json`、`draft_info.json`、缓存、封面图或导出视频。
- 不能提交用户素材路径、微信临时路径、桌面路径、客户视频、商业音乐、字幕原稿和真实项目输出。
- 不能提交账号、Cookie、token、OAuth 缓存、会员状态、支付信息。
- 不能写破解、绕过会员、绕过登录、自动点击付费或自动发布流程的脚本。

## 下一步

1. 保持 `examples/capcut_jianying_bridge/probe.py` 只读。
2. 增加草稿目录结构检查，但不打印真实素材路径。
3. 本机临时验证 `pyJianYingDraft` 与 `pyCapCut` 的最小草稿生成能力。
4. 选择一个模板替换实验：标题、字幕、图片和一段视频。
5. 评估是否需要单独的本地 MCP 服务，而不是把剪映逻辑塞进通用状态检查脚本。
