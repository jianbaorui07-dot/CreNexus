# vector-delivery-v1

状态：`experimental`。它是普通用户的推荐矢量交付工作流；现有四模式入口继续作为隐藏兼容能力保留。领域模型、持久化、确认门、实际 SVG/预览/报告登记、Evidence、桌面项目/任务/交付入口和小图集成测试已经存在；真实 Windows 发布验收与 Illustrator AI 副本尚未完成。

```text
明确选择 PNG/JPEG
→ 校验并确认复制到项目 source
→ 精确像素重建
→ 验证 SVG 无位图、脚本和外链
→ 保存精确基线
→ 用户选择匠心、智能或轻量
→ 生成绘制型矢量
→ 渲染对比和质量指标
→ needs_user 审查
→ 收集实际存在的 SVG/预览/报告/Evidence
→ 交付
```

精确重建失败或超限时必须停止；不得调用或回退到 Illustrator Image Trace。当前工作流不声称已经生成 `.ai`；未来 Illustrator 写入必须绑定 SVG hash、revision 和一次性 approval，回读或提交失败时回滚。任何步骤都不得覆盖源文件。

只有普通用户入口、校验、确认、真实输出、状态、失败/取消或回滚、质量验证、脱敏 Evidence、自动测试和真实 Windows 验收全部存在后，产品状态才能升级为 `stable`。
