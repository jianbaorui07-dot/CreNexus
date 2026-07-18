# comfyui-generation-v1

状态：`experimental`。已复用现有 workflow validate、txt2img submit、history 和 `/view` 回读并接入统一 Workflow Engine，不复制独立任务系统。模拟回环 ComfyUI 的集成测试覆盖 dry-run、探测、确认提交、同一 prompt 结果读取、真实字节复制、哈希登记和脱敏 Evidence；真实本机 ComfyUI 尚未验收。

```text
选择或创建 Project
→ 填写提示词和参数
→ 指定本机 checkpoint 文件名/尺寸/采样设置
→ 校验 workflow JSON
→ 生成脱敏 dry-run 摘要
→ needs_user 确认
→ 提交本机 ComfyUI 队列
→ 轮询进度
→ 收集结果 basename/hash
→ 写入 Project artifacts、CreativeJob 和 Evidence
```

probe 只访问配置的回环 HTTP 地址；服务不存在时结构化失败且不请求 `/prompt`。提示词、模型名和完整 workflow 只保存在有期限、有容量上限的进程内保险库；持久化 plan 与 Evidence 只记录参数摘要、workflow hash、basename、SHA-256 和受控相对路径。证据不得保存提示词中的客户机密、模型真实路径、token、账号状态或生成图片内容。未经一次性确认不得请求 `/prompt`；提交状态不明时不得自动重复提交。
