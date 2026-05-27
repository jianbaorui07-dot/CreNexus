# CAD / DXF Bridge Demo Scenarios

以下场景只描述安全 demo，不调用真实 AutoCAD，不写真实 DWG，不读取客户图纸。

## 1. Codex 验证 CAD plan

Codex 读取 `examples/cad/example_plan.json`，调用 `validate_cad_plan(plan)`，返回统一 JSON。非法实体、缺失字段和未知类型通过 `ok=false`、`warnings`、`next_steps` 表达。

## 2. Codex 从 prompt 生成 cad_plan

Codex 读取 `examples/cad/example_prompt.txt`，调用 `create_dxf_plan(prompt)`，得到包含矩形边框、辅助线和标题文字的中间计划。这个计划只存在于 JSON 中，不写真实 CAD 文件。

## 3. Codex dry-run 生成 DXF

Codex 调用 `write_dxf(plan, output_path, dry_run=True)`。该命令只返回计划摘要，不写 DXF 文件。

## 4. Codex 统计图层和实体数量

Codex 调用 `summarize_plan(plan)`，得到图层数量、实体总数，以及 line、polyline、circle、rectangle、text 等实体类型统计。

## 5. 未来接入 AutoCAD 打开 DXF 验证

后续可在用户明确确认后，把 `examples/cad/output/` 中的测试 DXF 用 AutoCAD 或 CAD viewer 打开验证。该步骤必须保持可选，不作为默认状态检查的一部分。
