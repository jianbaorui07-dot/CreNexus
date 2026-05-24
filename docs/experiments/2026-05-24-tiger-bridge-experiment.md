# 2026-05-24 老虎线稿本地桥接实验记录

本记录用于说明 Codex 本地创意软件桥在一次真实素材实验中的状态。实验素材是一张老虎黑白线稿图片；源图、导出图、DWG、Blender 文件和命令日志只保存在本机输出目录，不提交到 GitHub。

## 实验范围

| 软件桥 | 实验动作 | 结果 |
| --- | --- | --- |
| Photoshop | 通过 COM 调用主体选择 / `autoCutout`，从老虎线稿生成主体 PNG | 成功 |
| Illustrator / AI 矢量文件 | 用离线脚本把老虎线稿生成 SVG 预览，再通过 Illustrator COM 打开 SVG | 成功 |
| CAD / AutoCAD | 运行 CAD probe、AutoCAD MCP 协议测试，并用参考图转线稿脚本生成 DWG 预览 | 成功 |
| Blender | 使用运行中的 Blender 可执行文件生成老虎图 3D 展板场景和渲染图 | 成功 |
| ComfyUI | 运行 probe 和 txt2img 尝试，检查常见本地端口 | 未成功，服务未启动或路径失效 |

## 使用的公开命令

```powershell
python scripts\collect_bridge_status.py --json
python examples\comfy_bridge\probe.py --json
python examples\comfy_bridge\run_txt2img.py --prompt "black ink tiger line art, reference sketch experiment" --ckpt "tiger_demo_checkpoint.safetensors"
python examples\cad_bridge\probe.py --json
python scripts\test_autocad_mcp.py
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\probe.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<local-source-image>" -OutputPath "<local-output-png>"
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\probe.ps1
python examples\blender_bridge\probe.py --json
python scripts\trace_girl_rose_reference_to_cad.py --image "<local-source-image>"
```

## 关键观察

- Photoshop COM 可用，主体选择实验返回 `ok: true`，方法为 `autoCutout`。这是实验级抠图，不代表复杂商业图都能一次自动完成。
- Illustrator COM 可用，生成的 SVG 线稿预览可以被 Illustrator 打开。当前仍未完成 Image Trace、SVG/PDF/PNG 标准化导出脚本。
- AutoCAD COM 注册可检测，MCP 测试列出 11 个工具，并能保存公开测试 DWG。参考图转 CAD 线稿脚本能生成 DWG 和预览图，但对老虎图的 ROI 和阈值仍需专门调参。
- Blender 本机可执行文件可用，脚本生成了包含老虎参考图的 3D 展板 `.blend` 和渲染图。仓库探针仍需要后续通过 `BLENDER_EXE` 或更好的发现逻辑识别该安装。
- ComfyUI 默认地址 `127.0.0.1:8188` 无法连接，常见候选端口也无响应；开始菜单中的 ComfyUI 入口目标失效。本次没有生成 ComfyUI 图片。

## 本地成品

本次本地产物包括：

- Photoshop 主体 PNG。
- Illustrator 可打开的 SVG 线稿预览。
- AutoCAD MCP 测试 DWG。
- 老虎参考图转 CAD 线稿 DWG 和预览图。
- Blender 3D 展板 `.blend` 和渲染 PNG。
- ComfyUI 失败 JSON、probe report 和端口检查记录。

这些文件包含本机路径、生成图或二进制工程文件，只保存在本机，不进入 GitHub。

## 后续改进

1. 给 ComfyUI 增加本机 launcher 配置说明，避免快捷方式失效时无法启动服务。
2. 给 Blender probe 增加运行中进程和快捷方式发现能力，同时继续避免提交真实安装路径。
3. 把 Illustrator SVG 打开实验升级为参数化导出脚本。
4. 把 CAD 参考图转线稿脚本的 ROI、阈值和输出名称改成参数，避免沿用旧示例名称。
5. 为 Photoshop 抠图结果增加 alpha 统计和质量评分，方便判断背景是否真正去除。
