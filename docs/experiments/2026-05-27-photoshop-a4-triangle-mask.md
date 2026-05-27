# 2026-05-27 Photoshop A4 三角蒙版实验记录

本记录用于保存 Codex 通过 Photoshop 本地桥接完成一次版式实验的公开安全数据。源图、桌面成品、PSD、PNG、中间抠图、临时脚本和本机路径不提交到 GitHub，只保留在本机。

## 实验目标

在 Photoshop 中新建 A4 画布，将一张本地图片做主体抠图，处理为蓝黄渐变色调，并放入三角形蒙版区域内，最终导出本机成品。

## 环境与桥接状态

| 项目 | 结果 |
| --- | --- |
| 操作系统 | Windows |
| Photoshop 自动化方式 | COM + Photoshop JavaScript |
| Photoshop 版本 | 27.1.0 |
| COM 探针 | 成功 |
| 主体抠图方法 | `autoCutout` |
| 公开仓库产物 | 本实验记录 |
| 本机产物 | PNG / PSD / 中间透明 PNG，仅本机保存 |

## 公开可复现流程

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "<local-output-png>"
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<local-source-image>" -OutputPath "<local-cutout-png>"
```

后续 A4 合成在本机临时输出目录中执行，不把真实源图路径、桌面路径或输出文件写入仓库。可公开复现的关键步骤是：

1. 用 Photoshop COM 探针确认本机授权 Photoshop 可用。
2. 用 `extract_subject_to_png.ps1` 调用 Photoshop 主体选择能力生成透明主体 PNG。
3. 将透明主体转换为蓝黄渐变色调，保留原图明暗和细节纹理。
4. 在 Photoshop 中创建 A4 300dpi RGB 文档。
5. 将处理后的主体图层放入三角形图层蒙版区域。
6. 添加蓝黄边缘强调和浅色页面背景。
7. 导出本机 PNG 和保留图层的 PSD。

## 实验结果

| 检查项 | 结果 |
| --- | --- |
| Photoshop COM 连接 | `ok: true` |
| 抠图方法 | `autoCutout` |
| 抠图透明 PNG | 成功生成 |
| A4 合成画布 | `2480 x 3508 px` |
| 分辨率 | 约 `300dpi` |
| 色调处理 | 蓝黄渐变 |
| 三角形蒙版 | 成功 |
| PSD 图层保留 | 成功 |
| GitHub 发布边界 | 未提交源图、成品图、PSD、本机路径或临时输出 |

## 观察

- Photoshop 的 `autoCutout` 可以作为 Codex 本地抠图桥接的有效起点，但复杂抽象图像仍可能需要人工精修。
- 对外发布时应记录流程、参数和结果摘要，而不是提交本机图片资产或输出文件。
- A4 画布尺寸 `2480 x 3508 px` 对应 300dpi 竖版页面，适合作为后续海报、报告插图或版式模板的基础。
- 三角形图层蒙版适合把高细节科技图像收束到明确版式区域，避免直接发布完整素材图。

## 后续改进

1. 将 A4 合成步骤整理成参数化公开脚本，输入和输出路径全部由参数传入。
2. 为 Photoshop 抠图结果增加 alpha 像素统计和主体边界报告。
3. 增加可选的版式参数，例如三角形顶点、边框颜色、输出尺寸和背景色。
4. 在不提交素材的前提下，提供一个纯生成测试图用于 CI 或本地演示。
