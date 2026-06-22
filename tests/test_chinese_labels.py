from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class ChineseLabelCoverageTest(unittest.TestCase):
    def read_text(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_readme_has_clear_chinese_regions(self) -> None:
        readme = self.read_text("README.md")

        self.assertIn("中文阅读指南", readme)
        self.assertIn("仓库区域标注", readme)
        self.assertIn("图像生成区", readme)
        self.assertIn("工程制图区", readme)
        self.assertIn("AI 矢量文件桥", readme)

    def test_comfy_readme_uses_chinese_area_labels(self) -> None:
        readme = self.read_text("examples/comfy_bridge/README.md")

        self.assertIn("区域一：这个目录做什么", readme)
        self.assertIn("区域三：文件中文标注", readme)
        self.assertIn("命令行参数中文说明", readme)

    def test_cad_scripts_include_chinese_drawing_labels(self) -> None:
        connection_plate = self.read_text("scripts/draw_connection_plate_from_spec.py")
        reference_part = self.read_text("scripts/draw_reference_mechanical_part.py")

        for content in (connection_plate, reference_part):
            self.assertTrue("主圆孔区" in content or "大圆基准区" in content)
            self.assertIn("中心线基准", content)
            self.assertIn("公开演示", content)

    def test_chinese_label_standard_is_indexed(self) -> None:
        index = self.read_text("docs/中文用途索引.md")
        standard = self.read_text("docs/中文标注规范.md")

        self.assertIn("docs/中文标注规范.md", index)
        self.assertIn("每个区域必须有中文名称", standard)
        self.assertIn("每张示例 CAD 图必须有中文区域标注", standard)

    def test_starbridge_protocol_links_photoshop_practice(self) -> None:
        protocol = self.read_text("docs/starbridge-link-protocol.md")
        index = self.read_text("docs/中文用途索引.md")

        self.assertIn("星桥链接协议", protocol)
        self.assertIn("Photoshop 本机接入实操", protocol)
        self.assertIn("diagnose_local.ps1", protocol)
        self.assertIn("document_info.ps1", protocol)
        self.assertIn("run_local_practice.ps1", protocol)
        self.assertIn("write_practice_report.py", protocol)
        self.assertIn("故障排查表", protocol)
        self.assertIn("产物清单", protocol)
        self.assertIn("验收标准", protocol)
        self.assertIn("透明像素统计", protocol)
        self.assertIn("主体边界", protocol)
        self.assertIn("AI 矢量文件桥", protocol)
        self.assertIn("Adobe Illustrator 的 `.ai`", protocol)
        self.assertIn("整体方案和本机实例对照", protocol)
        self.assertIn("本机没有时怎么补", protocol)
        self.assertIn("星桥链接协议入口", index)

    def test_illustrator_vector_bridge_is_indexed(self) -> None:
        readme = self.read_text("README.md")
        protocol = self.read_text("docs/starbridge-link-protocol.md")
        index = self.read_text("docs/中文用途索引.md")
        illustrator_doc = self.read_text("docs/05-codex-illustrator.md")
        bridge_status = self.read_text("examples/bridge_status.py")

        self.assertIn("docs/05-codex-illustrator.md", readme)
        self.assertIn("docs/05-codex-illustrator.md", protocol)
        self.assertIn("docs/05-codex-illustrator.md", index)
        self.assertIn("AI 矢量文件", illustrator_doc)
        self.assertIn("ILLUSTRATOR_EXE", illustrator_doc)
        self.assertIn("trace_image_to_vector", illustrator_doc)
        self.assertIn("def check_illustrator", bridge_status)
        self.assertIn("Illustrator.Application", bridge_status)

    def test_local_instance_comparison_covers_missing_local_apps(self) -> None:
        protocol = self.read_text("docs/starbridge-link-protocol.md")
        bridge_status = self.read_text("examples/bridge_status.py")
        readme = self.read_text("README.md")

        self.assertIn("剪映/CapCut 草稿桥", protocol)
        self.assertIn("JIANYING_DRAFTS_DIR", protocol)
        self.assertIn("CAPCUT_DRAFTS_DIR", protocol)
        self.assertIn("def check_jianying_capcut", bridge_status)
        self.assertIn("CAPCUT_EXE", bridge_status)
        self.assertIn("剪映可执行文件", readme)


if __name__ == "__main__":
    unittest.main()
