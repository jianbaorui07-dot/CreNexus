# StarBridge 官网候选

这是未发布的静态官网源码，不是桌面应用，也没有与现有 `chatgpt.site` 建立可验证部署关系。

```powershell
npm.cmd run site:build
```

输出到 `apps/starbridge-site/dist/`。构建脚本读取根目录 `brand/brand-tokens.json`，因此官网与桌面共享品牌事实源。候选下载页当前指向 GitHub 上真实存在的未签名内部预览安装包，并明确区分内部测试与正式签名发布。正式部署前仍需确认域名、托管平台、隐私条款和下载产物。
