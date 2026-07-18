# StarBridge Illustrator UXP（自定义实验宿主）

这是用户自定义 Illustrator UXP 运行时的实验插件，不声明 Adobe 官方 Marketplace 兼容性。插件只连接本机 `ws://127.0.0.1:8972/illustrator`。

## 功能

- 每 500 ms 推送活动文档、选择、图层、画板、缩放和工具的脱敏摘要。
- 支持原有七个会话方法，以及匠心映射的应用、回读、提交和回滚四个事务方法。
- 写操作必须包含 `confirm_write=true`。
- 匠心映射先解析全部稳定目标再写入；回读或提交失败时由调用端触发回滚。
- 不接受文件路径、任意 JSX 或任意 JavaScript。
- 不读取链接资产路径、字体路径、账号或 Creative Cloud 状态。

## 本机加载

使用你自己的 Illustrator UXP 开发加载器载入本目录。若自定义宿主标识不是 `ILST`，只在本机修改 manifest；不要把本机安装路径或账号信息写回仓库。

先启动代理：

```powershell
npm.cmd run illustrator:realtime:proxy
```

面板显示 `connected` 和 `synced` 后，可通过代理的 `/state` 与 `/rpc` 接口联调。
