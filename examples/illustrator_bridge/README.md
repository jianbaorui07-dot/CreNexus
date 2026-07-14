# Illustrator / AI 矢量文件桥

这个目录提供 Windows-first Illustrator 环境探测、sandbox demo、实时状态原型，以及受控彩色 Image Trace 原型。彩色矢量化默认只返回计划；真实执行只接受用户明确传入的单张 PNG/JPEG，运行固定 JSX，并把 AI/SVG/PNG 写入忽略目录 `examples/output/illustrator/`。

## probe 做什么

- 检查当前系统是否 Windows。
- 检查 `ILLUSTRATOR_EXE` 是否配置并存在。
- 检查 `Illustrator.Application` COM 类型是否可用。
- 输出统一安全 JSON report。

## probe 不做什么

- 不打开客户 `.ai`。
- 不读取源图、字体、商业画笔或购买素材。
- 不保存导出结果。

## 彩色矢量化安全边界

- `protocols/color_vectorization.v1.schema.json` 固定输入授权、Image Trace 参数和质量闸门。
- `scripts/color_vectorize.ps1` 默认 dry-run；真实执行要求 `ConfirmWrite` 与 `ConfirmExport`。
- 只连接已运行的授权 Illustrator，不接收任意 JSX，不扫描素材目录，不上传云端。
- 白色默认保留；生成结果必须经过 PNG 预览和外部指标复核，不能把 Image Trace 自动等同于“原样通过”。

## 命令

```powershell
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\probe.ps1
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\scripts\color_vectorize.ps1
```

完整说明见 [`docs/color-faithful-vectorization.md`](../../docs/color-faithful-vectorization.md)。
