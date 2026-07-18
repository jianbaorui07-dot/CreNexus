# 官网源码与部署关系

仓库审计没有找到用户提到的 `chatgpt.site` 页面对应的可编辑源码、构建配置、部署凭据或域名映射，因此本轮不能声称已修改线上网站。

正式官网候选建立在 `apps/starbridge-site/`，是可离线构建的静态站点。它从 `brand/brand-tokens.json` 读取共享品牌 token，并生成 `/`、`/features`、`/editions`、`/workflows`、`/privacy`、`/docs`、`/download`、`/roadmap`、`/support`。

当前关系：

- 源码：`apps/starbridge-site/`
- 构建产物：`apps/starbridge-site/dist/`（Git 忽略）
- 线上发布：未执行
- `chatgpt.site` 映射：未找到证据
- 下载按钮：未开放；下载页明确显示签名和干净机器验收尚未完成

未来发布前必须由站点所有者确认实际托管平台、域名、部署权限、隐私条款和下载产物哈希。不得仅凭本地页面存在就宣称线上网站已更新。
