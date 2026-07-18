# StarBridge 离线商业化边界

本文说明 Community、未来 Pro 与 Enterprise 的离线授权事实。机器可读状态以 [`product/product-manifest.json`](../product/product-manifest.json) 为准。当前已交付的是授权协议与验签基础，不代表 Pro 功能、收费发布或生产签发体系已经交付。

## 不变原则

- Community 免费功能无需登录、联网或授权文件。
- 图片、设计文件、任务记录和授权文件留在本机；不上传，不收集遥测。
- 桌面后端仅绑定 loopback；临时会话凭据留在 Rust 层，不暴露给 WebView。
- 所有写入继续受 safe roots 与 `confirm_write`、`confirm_export`、`confirm_run` 约束。
- 生产签名私钥不得进入任何 Git 仓库、安装包、日志或客户电脑。
- Community 二进制不得包含私有 Pro 实现；公开 MIT 能力不能重新包装成 Pro 独占功能。

## Community 与 Pro

Community 已公开的匠心矢量、智能矢量、轻量矢量、精确重建以及现有创意软件协议继续属于开放核心。基础 Project、CreativeJob、单任务历史、基础交付和脱敏 Evidence 是公共工作流基础。未来 Pro 的价值来自批量、并发、安全检查点、高级恢复/保留策略、商业规范、新的私有增强、稳定签名安装包和专业支持，而不是把同一份公开算法或基础项目能力再次收费。

建议价格仍是：Community `¥0`；Pro 早鸟永久版建议 `¥399`；Enterprise 按项目报价。`¥399` 只是建议，不是正式开售。未决条款见 [`PRO_COMMERCIAL_TERMS_DRAFT.md`](PRO_COMMERCIAL_TERMS_DRAFT.md)。

## 三步人工激活

1. **导出设备申请**：应用生成 `.starbridge-request`。文件只含带域前缀的设备哈希、申请编号、产品和版本信息，不含原始 `MachineGuid`、图片、设计文件或任务内容。
2. **完成人工购买**：用户通过双方约定的人工渠道发送申请文件。StarBridge 应用不会连接授权服务器。运营人员只能在隔离的签发环境中处理申请。
3. **导入授权文件**：用户选择 `.starbridge-license`；Rust 层先验证 schema、product ID、key ID、Ed25519 签名、设备数量、功能白名单和当前设备，再原子写入 `%LOCALAPPDATA%\StarBridge\license`。

授权文件支持 1–2 台设备，但默认 1 台还是 2 台仍由产品所有者决定。换机、重装和主板更换规则也尚未定案。

## 授权文件 v1

签名输入使用 RFC 8785 JSON Canonicalization Scheme，签名算法为 Ed25519。示例中的 key、哈希和签名均不可用于生产。

```json
{
  "schema": "starbridge-license/v1",
  "payload": {
    "product_id": "starbridge-desktop",
    "license_id": "SB-PRO-EXAMPLE-001",
    "edition": "pro",
    "issued_on": "2026-07-17",
    "perpetual": true,
    "device_limit": 1,
    "device_fingerprints": ["sb-device-v1:<HASH>"],
    "features": ["workflow.production_vector", "batch.processing"]
  },
  "signature": {
    "algorithm": "ed25519",
    "key_id": "starbridge-production-v1",
    "value": "<BASE64URL_SIGNATURE>"
  }
}
```

应用只返回脱敏授权编号、授权版本、设备数量、当前设备匹配状态、功能列表和权益摘要；不显示完整设备指纹、完整授权文件、生产公钥内容或签名输入。

## 验证与恢复

现有 Rust 测试覆盖：签名篡改、payload 篡改、错误设备、错误 product ID、错误 schema、未知 key ID、重复功能、未知功能、设备超限、超大文件、空文件、非 JSON、非法 Unicode 功能名、脱敏编号、当前/上一把公钥轮换以及原子写入中断后的备份恢复。

正式构建可在编译期注入当前公钥和一把上一代公钥，以便短期密钥轮换兼容；Community 开发构建默认不包含生产公钥。恢复逻辑只扫描应用自己的授权目录，不扩大 safe roots。

## 离线更新包

未来流程是：用户取得更新包 → 应用选择文件 → 本机验签 → 展示版本和说明 → 用户明确确认 → 创建恢复点或备份 → 执行更新 → 验证 → 失败回滚。

本轮只有架构和界面状态，不包含真实更新执行。禁止无签名更新、后台下载、静默安装、远程停用、联网撤销永久许可证或把更新私钥放进安装包。

## 当前发布事实

- 当前 NSIS 安装包曾在本开发机完成安装、启动、关闭和卸载，但仍是 `NotSigned`。
- 没有生产公钥、生产私钥或正式离线签发工具。
- 没有创建私有 `StarBridge-Pro` 仓库。
- GitHub 已提供可直接下载的未签名内部预览 prerelease，供团队安装测试；这不等于正式签名版或收费发布。
- 代码签名、干净 Windows、Defender、SmartScreen、正式条款、退款、税务和支持期限仍是发布门槛。

详细门槛见 [`WINDOWS_RELEASE_READINESS.md`](WINDOWS_RELEASE_READINESS.md)，源码组合边界见 [`PRIVATE_PRO_ARCHITECTURE.md`](PRIVATE_PRO_ARCHITECTURE.md)。
