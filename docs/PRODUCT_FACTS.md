# StarBridge 产品事实

本文与 `product/product-manifest.json` 共同构成产品状态的单一事实源。当前产品版本为 `0.1.0-alpha.0`；Python 包使用等价的 PEP 440 版本 `0.1.0a0`。能力矩阵的修订号不是产品版本。

## 状态语言

能力状态只能是：

- `stable`：该能力声明的完整范围已有与范围匹配的自动验证；涉及真实软件写入时，还必须有经审查的本机授权软件证据。
- `experimental`：已有实现或协议证据，但真实环境、失败恢复、发布验证或用户入口仍不完整。
- `planned`：架构或路线已经确定，不能描述为可用。
- `not_implemented`：明确没有实现，或属于安全边界内禁止提供的能力。

以下字段不能替代能力状态：

- `recommended` 表示产品是否主推；原来的 `primary` 应映射到这里。
- `evidenceLevel` 只描述证据强度：`none / schema / unit / integration / local_app / release`。
- `connectionState` 是运行时探针结果：`unknown / not_installed / available / not_running / connected / error`。静态文档默认只能写 `unknown`。

协议测试、mock、存在可执行文件或安装了 `pywin32` 都不能单独证明软件处于 `connected`。

## 当前发布事实

- Community 为公开 MIT 开放核心，无需激活。
- Pro 和 Enterprise 均为 `planned`，没有开售。
- 四种离线矢量化引擎属于 Community。
- 基础 Project、CreativeJob、Workflow Engine、单任务历史、基础交付和脱敏 Evidence 已有 Community 实现与集成测试，状态为 `experimental`。
- `vector-delivery-v1`、`comfyui-generation-v1` 和 `photoshop-production-v1` 已接入统一任务系统；前者在离线小图夹具上完成闭环，后两者分别通过模拟回环服务和模拟 UXP 代理闭环。三者都尚未获得发布级或真实第三方软件写入验收。
- 批量队列、并发、检查点、高级恢复和商业策略属于未来 Pro。
- 本地曾构建未签名 NSIS，但没有公开安装包、生产更新公钥、Authenti­code、干净 Windows、完整 Defender、SmartScreen 或公开升级证据。
- 软件更新代码属于 `experimental` 且 not live。

## 运行时连接事实

桌面端必须从当前 probe 生成连接状态，不能从 README、manifest 或“存在代码”推断。真实写入只有在当前授权会话探测成功、用户明确确认、输入 hash/revision/approval 匹配且结果回读通过后才成立。

运行以下命令校验机器可读事实：

```powershell
python scripts\check_product_facts.py
python scripts\check_text_encoding.py
python examples\bridge_status.py --json --redact-paths --soft-exit
```
