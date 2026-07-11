from __future__ import annotations

import unittest

from starbridge_mcp.core.transaction import CreativeTransaction, create_recipe_transaction


class CreativeTransactionTests(unittest.TestCase):
    def test_safe_recipe_transaction_defaults_to_planned_dry_run(self) -> None:
        transaction = create_recipe_transaction(
            recipe_id="public_preview",
            bridge="photoshop",
            intent="Create a public sandbox preview",
            steps=[{"tool": "photoshop.session_info"}],
            quality_gates=["sandbox_only"],
            expected_outputs=["redacted manifest"],
        )
        payload = transaction.to_dict()

        self.assertEqual("planned", payload["status"])
        self.assertEqual("L2", payload["risk_level"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual(["validated", "failed", "aborted"], payload["allowed_next_statuses"])
        self.assertFalse(payload["rollback_plan"]["destructive_actions_allowed"])

    def test_invalid_transition_is_rejected(self) -> None:
        transaction = CreativeTransaction(intent="Inspect public metadata", bridge="all", risk_level="L1")
        with self.assertRaisesRegex(ValueError, "invalid transaction transition"):
            transaction.transition_to("running")

    def test_confirmed_write_is_l3_and_requires_approval(self) -> None:
        transaction = create_recipe_transaction(
            recipe_id="sandbox_write",
            bridge="cad",
            intent="Write a reviewed DXF into sandbox",
            steps=[],
            quality_gates=["sandbox_only"],
            expected_outputs=["sandbox DXF"],
            dry_run=False,
        )

        self.assertEqual("L3", transaction.risk_level)
        self.assertIn("user_confirmation_before_write", transaction.required_approvals)


if __name__ == "__main__":
    unittest.main()
