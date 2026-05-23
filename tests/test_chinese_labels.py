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
        self.assertIn("星桥链接协议入口", index)


if __name__ == "__main__":
    unittest.main()
