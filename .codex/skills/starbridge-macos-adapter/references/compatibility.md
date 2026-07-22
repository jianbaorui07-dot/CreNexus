# CreNexus macOS 能力边界

本表记录阶段 1 导入时可由仓库内容确认的边界，不代替 macOS 实机或桌面软件验收。

| 能力 | 阶段 1 结论 | 边界 |
| --- | --- | --- |
| Python MCP、安全扫描、safe-only tools | 可运行跨平台命令 | 必须以当前 Python 环境的实际结果为准 |
| 版本协调器 self-test | 有 Python CLI 入口 | 仅离线验证；不安装软件、不检查许可 |
| Illustrator realtime proxy | 有 localhost Node proxy 和协议测试 | 已有 adapter 启动入口是 PowerShell；尚未导入 macOS 原生 adapter |
| Illustrator Apple Events / SVG 保存为 AI | 未在当前仓库找到受审计的 macOS 脚本 | 不生成 AppleScript，不声称可用 |
| Illustrator WGC capture | Windows 实现 | macOS 为 `unsupported_platform` |
| Photoshop bridge | 有既有 UXP / Node proxy 路线 | 本 Skill 不新增 AppleScript，也不验证本机 Adobe |
| AutoCAD COM | Windows executor | macOS 为 `remote_executor_required` |
| ComfyUI / Blender | 协议和计划层可跨平台 | 用户自行启动本地服务；不扫描模型或资产目录 |

## macOS 使用规则

1. 使用 POSIX 路径和 `python3`/`npm`，不要执行 `npm.cmd` 或 Windows COM/PowerShell 入口。
2. 没有经过实机验证的桌面功能必须标为未验证，不能以源码、文档或 Windows 测试替代。
3. 需要安装开发工具、依赖或授予 macOS 权限时，说明命令和影响并由用户手动决定；不得自动执行。
4. 任何真实 Adobe 写入、导出或客户矢量交付，都应改由相应软件 Skill 的明确确认流程处理。
