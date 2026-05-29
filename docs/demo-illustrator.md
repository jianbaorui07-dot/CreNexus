# Illustrator sandbox demo

## 目标

证明 AI / Illustrator 桥已经不是 planned-only：它可以在本机创建公开安全的测试矢量画板，并导出 SVG、PNG preview 和 PDF proof。

这个 demo 只使用脚本生成的基础矢量元素，不读取私有 `.ai` 文件，不使用外部素材。

参考设计来源：

- `loonghao/photoshop-python-api-mcp-server`：仅参考 Adobe 桌面软件通过本机自动化暴露 document/session 工具的组织方式。
- `ie3jp/illustrator-mcp-server`：仅参考 JSX / ExtendScript、MCP tools、导出和文档信息工具的组织方式。

参考仓库保存在本机 `external_references/`，不提交到 Git。实现代码按 StarBridge 的 dry-run、confirm 和 sandbox 输出边界重写。

## 前置条件

- Windows
- Adobe Illustrator desktop 已授权可用
- PowerShell
- `Illustrator.Application` COM 可用

## 命令

```powershell
npm.cmd run illustrator:info
npm.cmd run illustrator:demo:plan
npm.cmd run illustrator:demo
npm.cmd run illustrator:manifest
```

`illustrator:demo:plan` 是默认安全路径，不写文件。真实 demo 由 `run_demo.ps1` 内部显式传入 `-ConfirmWrite` 和 `-ConfirmExport`，输出仍限制在 sandbox 目录。

## 输出位置

```text
examples/output/illustrator/
```

生成的 `.ai`、`.svg`、`.png`、`.pdf` 和 manifest JSON 都被 `.gitignore` 忽略。

## 安全边界

- 不读取私有 `.ai`
- 不提交客户图稿
- 不提交导出文件
- 不使用商业字体
- 不写个人绝对路径
- Image Trace 仍是下一阶段能力，本 demo 不声称已完成图像描摹
