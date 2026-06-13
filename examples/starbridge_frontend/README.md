# StarBridge Creative Console

这是一个公开安全的前端示例，用于展示 StarBridge / Codex 接入本地创作软件的能力矩阵、验证命令和安全边界。

## 本地运行

```powershell
cd examples\starbridge_frontend
npm install --package-lock=false
npm run dev
```

## 构建

```powershell
npm run build
```

## 发布边界

- 不包含 PSD、AI、DWG、模型、生成图片或客户素材。
- 不写入个人桌面路径、软件安装路径、账号信息或 token。
- 页面里的命令以只读、dry-run 或脱敏检查为主。
- 真正的软件写入能力仍以仓库脚本和 MCP tool 的显式确认策略为准。
