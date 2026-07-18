from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_ADAPTER = ROOT / "uxp" / "illustrator-bridge" / "src" / "host-adapter.js"


@unittest.skipUnless(HOST_ADAPTER.exists(), "Illustrator host adapter missing")
class IllustratorArtisanHostTests(unittest.TestCase):
    def run_node(self, body: str) -> dict:
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is not installed")
        source = f'import {{ IllustratorHostAdapter }} from "{HOST_ADAPTER.as_uri()}";\n' + body
        completed = subprocess.run(
            [node, "--input-type=module", "-e", source],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return json.loads(completed.stdout)

    def test_apply_readback_and_rollback_are_transactional(self) -> None:
        result = self.run_node(
            """
const layer = {name: "layer-subject", locked: false, hidden: false};
const item = {name: "shape-0002", locked: false, hidden: false};
const document = {layers: [layer], pageItems: [item], views: [], artboards: []};
const adapter = new IllustratorHostAdapter(); adapter.app = {activeDocument: document};
const params = {transaction_ref: "apply:0123456789ab", map_ref: "imap:abcdef012345", expected_state_revision: 7, layers: [["layer-subject", "主体色块"]], objects: [["shape-0002", "朱红装饰"]]};
const applied = await adapter.execute("illustrator.apply_artisan_map", params);
const readback = await adapter.execute("illustrator.readback_artisan_map", params);
const rollback = await adapter.execute("illustrator.rollback_artisan_map", params);
const reapplied = await adapter.execute("illustrator.apply_artisan_map", params);
const committed = await adapter.execute("illustrator.commit_artisan_map", params);
const next = {...params, transaction_ref: "apply:111111111111", layers: [["layer-subject", "主体终稿"]], objects: [["shape-0002", "朱红终稿"]]};
const nextApplied = await adapter.execute("illustrator.apply_artisan_map", next);
const nextRollback = await adapter.execute("illustrator.rollback_artisan_map", next);
console.log(JSON.stringify({applied, readback, rollback, reapplied, committed, nextApplied, nextRollback, layer: layer.name, item: item.name, transactions: adapter.nameTransactions.size, stableTargets: adapter.stableTargetMap.size}));
"""
        )
        self.assertTrue(result["applied"]["ok"])
        self.assertTrue(result["readback"]["ok"])
        self.assertEqual(result["rollback"]["restored"], 2)
        self.assertEqual(result["committed"]["committed"], 2)
        self.assertTrue(result["nextApplied"]["ok"])
        self.assertEqual(result["nextRollback"]["restored"], 2)
        self.assertEqual(result["layer"], "主体色块")
        self.assertEqual(result["item"], "朱红装饰")
        self.assertEqual(result["transactions"], 0)
        self.assertEqual(result["stableTargets"], 2)

    def test_missing_target_does_not_partially_rename(self) -> None:
        result = self.run_node(
            """
const layer = {name: "layer-subject", locked: false, hidden: false};
const document = {layers: [layer], pageItems: [], views: [], artboards: []};
const adapter = new IllustratorHostAdapter(); adapter.app = {activeDocument: document};
let error = null;
try { await adapter.execute("illustrator.apply_artisan_map", {transaction_ref: "apply:0123456789ab", map_ref: "imap:abcdef012345", layers: [["layer-subject", "主体色块"]], objects: [["shape-9999", "缺失对象"]]}); }
catch (caught) { error = caught.message; }
console.log(JSON.stringify({error, layer: layer.name}));
"""
        )
        self.assertEqual(result["error"], "stable_name_target_not_unique")
        self.assertEqual(result["layer"], "layer-subject")

    def test_transaction_refuses_to_touch_a_different_document(self) -> None:
        result = self.run_node(
            """
const item = {name: "shape-0002", locked: false, hidden: false};
const first = {layers: [], pageItems: [item], views: [], artboards: []};
const second = {layers: [], pageItems: [], views: [], artboards: []};
const adapter = new IllustratorHostAdapter(); adapter.app = {activeDocument: first};
const params = {transaction_ref: "apply:0123456789ab", map_ref: "imap:abcdef012345", layers: [], objects: [["shape-0002", "朱红装饰"]]};
await adapter.execute("illustrator.apply_artisan_map", params);
adapter.app.activeDocument = second;
let error = null;
try { await adapter.execute("illustrator.rollback_artisan_map", params); }
catch (caught) { error = caught.message; }
console.log(JSON.stringify({error, firstItem: item.name}));
"""
        )
        self.assertEqual(result["error"], "artisan_transaction_document_changed")
        self.assertEqual(result["firstItem"], "朱红装饰")


if __name__ == "__main__":
    unittest.main()
