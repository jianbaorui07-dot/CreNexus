# photoshop-production-v1

状态：`experimental`，证据等级：`integration`。固定协议、Node Proxy、UXP handler、通用 CreativeJob、桌面普通用户入口和模拟端到端测试已经存在；尚未在当前用户授权的真实 Photoshop 会话中完成写入验收，因此不能显示为稳定或已连接。

## 固定流程

```text
选择已明确导入项目的一张 PNG/JPEG
→ 校验托管相对路径和 SHA-256
→ 只读探测 Node Proxy、UXP 和 Photoshop host
→ 只读读取活动文档尺寸、分辨率和图层数量
→ 用户确认 plan hash / revision / safe root
→ 复制活动文档为 StarBridge Sandbox Copy
→ 导入项目图片为固定命名图层
→ 可选调整画布
→ 应用固定亮度、对比度和饱和度调整层
→ 可选选择主体并导出透明 PNG
→ 先写应用拥有的临时文件
→ 全部成功后提升为 PNG / JPEG / PSD 交付文件
→ 计算 SHA-256 并回读验证
→ 用户确认结果
→ 进入统一交付与证据
```

## 安全边界

- 不接受任意 BatchPlay descriptor、JSX 或脚本。
- 源素材必须位于 `%LOCALAPPDATA%/StarBridge/projects` 或显式配置的等价应用数据根，并与计划 SHA-256 一致。
- 输出只能位于同一应用数据根的 `artifacts/<projectId>/<jobId>`。
- Node Proxy 与 Python adapter 独立校验输入和输出边界。
- 所有真实写入都在明确确认后发生，并且先复制活动文档；源文件和原活动文档不覆盖。
- UXP modal history 和 auto-close 控制负责失败回滚；Node Proxy 只清理该任务精确命名的应用临时文件。
- CreativeJob plan、runtime 和 Evidence 不保存活动文档名、图层名、绝对路径或客户图片内容。
- 软件未连接或没有活动文档时返回 `needs_user`，不会把 mock 当作真实成功。

## 当前验证边界

自动测试证明固定参数校验、确认门、断线恢复、受控路径、源 hash、临时输出清理、实际字节登记、SHA-256、Evidence 脱敏和桌面任务建立。真实 Photoshop 版本差异、主体选择成功率、PSD/JPEG/PNG UXP 导出以及模态失败恢复仍需经过用户明确确认后的 Windows 本机验收。
