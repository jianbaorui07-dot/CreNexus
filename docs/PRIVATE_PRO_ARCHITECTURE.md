# 私有 Pro 架构

状态：**边界设计完成；远程私有仓库未创建。** 建议未来仓库名为 `StarBridge-Pro`，创建前必须得到产品所有者的再次明确确认。

## 组合模型

公开 Community 仓库负责安全本地运行核心、公共接口、Community 功能、公开验签接口、产品 Manifest、Community UI 和公共测试。私有 Pro 仓库负责批量引擎、项目历史、可恢复任务、商业 UI 扩展、新的私有算法增强、商业软件工作流增强、离线签发工具、生产公钥注入、签名离线更新包构建、商业安装配置和企业定制。

私有仓库不复制整个公开仓库形成长期漂移的 Fork。商业构建应固定引用一个经过审计的 Community commit 或发布版本，再链接私有实现。

## 编译期边界

建议公共仓库暴露稳定接口包，例如：

```text
starbridge-community
├─ runtime-api          公共、本地、安全接口
├─ community-features   MIT 实现
├─ licensing-verifier  公开验签协议与类型
└─ desktop-shell        Community UI 与扩展插槽

StarBridge-Pro（未来私有）
├─ pro-batch-engine
├─ pro-project-store
├─ pro-workflow-enhancements
├─ issuer-offline
└─ commercial-build
```

商业构建通过显式依赖和构建清单链接私有模块；Community 构建的依赖图中不存在这些包。授权状态只能决定已链接商业模块是否可用，不能用 CSS 隐藏或布尔开关把完整 Pro 逻辑留在 Community 二进制里。

## 可测试约束

Community CI 必须证明：

- 依赖锁文件与最终二进制不含 `pro-*` 私有包、离线签发器或生产私钥；
- Community 构建没有生产公钥配置，除非未来产品所有者明确决定公开生产验签公钥；
- 禁止私有模块名称、签发命令和更新私钥路径出现在公开构建产物；
- 所有 public interface 都能用空实现或 Community 实现独立编译；
- 删除商业仓库凭据后，Community 仍可从干净 checkout 完整构建和测试。

商业 CI 必须证明：

- 固定 Community commit/版本与批准的 Manifest 相符；
- 私有模块只在商业构建图中链接；
- 生产公钥通过受控构建输入注入，生产私钥始终停留在隔离签发服务或硬件保护环境；
- 许可证拒绝、功能映射、签名更新包与回滚路径通过测试；
- 输出物签名、哈希和软件物料清单可追溯。

## 公开 MIT 能力的处理

匠心矢量、智能矢量、轻量矢量、精确重建，以及已经公开的 Illustrator、Photoshop、ComfyUI、Blender、CAD 协议和实现不能从历史上“收回”。未来 Pro 只能销售新增私有增强、生产工作流、交付和支持，详细证据见 [`COMMERCIAL_FEATURE_BOUNDARY_AUDIT.md`](COMMERCIAL_FEATURE_BOUNDARY_AUDIT.md)。

## 离线签发与更新

离线签发器属于私有运维工具，不随客户端分发。更新包生成器也在私有构建环境中运行；客户端只包含验签器和公开格式。更新必须由用户选择、确认、备份、执行、验证并支持失败回滚，不启用后台下载或远程停用。
