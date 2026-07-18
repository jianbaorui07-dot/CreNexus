# 给 Codex 的 3 分钟安装入口

把仓库链接发给 Codex 后，直接告诉它：

```text
请克隆这个仓库，进入仓库后运行 .\bootstrap.ps1 -Profile auto。
安装完成后打开一个新的 Codex task，并使用仓库里的 MCP 配置。
如果需要 Photoshop / Illustrator / AutoCAD / ComfyUI 的可选桥接，再运行
.\bootstrap.ps1 -Profile standard；需要全部可选矢量依赖时运行
.\bootstrap.ps1 -Profile all。
```

也可以在本机直接从链接安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-from-url.ps1 `
  -RepositoryUrl "https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software.git"
```

`auto` 会创建隔离的 `.venv`、安装可复用的 Python/MCP 和无桌面矢量依赖、安装本地 Codex MCP 配置，并运行安全自检。检测到本机桌面软件线索时会自动选择 `standard`。`standard` 和 `all` 才会安装 Node 代理和更重的可选包。

版本协同采用“能力探针优先”：Photoshop、Illustrator、AutoCAD、Blender、ComfyUI 和剪映/CapCut 的版本号只作为协同信息，不作为正版校验或版本白名单。桌面软件本身仍须由用户自行安装并按其许可使用；本项目不绕过登录、授权或激活。

安装脚本不会递归扫描私有目录，不会上传素材，不会把真实路径、账号、token 或 Cookie 写入 Git。`.codex/config.toml` 和 `.venv` 只保存在本机并已被 Git 忽略。
