# Photoshop sandbox demo

## 目标

证明 PS / Photoshop 桥可以创建安全测试 PSD、命名图层，并导出 PNG / JPG preview。这个 demo 只生成公开安全的色块和文本图层，不读取私有 PSD，不做复杂商业修图。

参考设计来源：

- `loonghao/photoshop-python-api-mcp-server`：仅参考 Windows COM / Photoshop 自动化和 document/layer/session 工具组织方式。
- `ie3jp/illustrator-mcp-server`：仅参考 Adobe 桌面 bridge 的 MCP tool 分层思路。

参考仓库保存在本机 `external_references/`，不提交到 Git。实现代码按 StarBridge 的 dry-run、confirm 和 sandbox 输出边界重写。

## 前置条件

- Windows
- Adobe Photoshop desktop 已授权可用
- PowerShell
- `Photoshop.Application` COM 可用

## 命令

```powershell
npm.cmd run photoshop:info
npm.cmd run photoshop:demo:plan
npm.cmd run photoshop:demo
npm.cmd run photoshop:manifest
```

`photoshop:demo:plan` 是默认安全路径，不写文件。真实 demo 由 `run_demo.ps1` 内部显式传入 `-ConfirmWrite` 和 `-ConfirmExport`，输出仍限制在 sandbox 目录。

## 输出位置

```text
examples/output/photoshop/
```

生成的 `.psd`、`.png`、`.jpg` 和 manifest JSON 都被 `.gitignore` 忽略。

## 安全边界

- 不读取私有 PSD
- 不提交客户图片
- 不提交导出文件
- 不用商业字体或商业笔刷
- 不写个人绝对路径
- 复杂商业修图、主体抠图和真实项目 PSD 仍然需要人工确认
