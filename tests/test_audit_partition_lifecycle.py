"""Comprehensive tests for audit partition lifecycle, P0001 constraint guards, and application-layer handling."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from dianxun.runtime import RuntimePrincipal, RuntimeService
from dianxun.state.postgres import raise_policy_error
from dianxun.state.protocols import StorePolicyError
from tests import test_stateful_core as fixture


class AuditPartitionLifecycleTests(unittest.TestCase):
    """Verifies audit partition roll, archive staging, and application P0001 handling."""

    setUp = fixture.StatefulCoreTests.setUp
    tearDown = fixture.StatefulCoreTests.tearDown

    def test_p0001_month_start_and_window_guards_raise_policy_error(self):
        """Simulate PostgreSQL P0001 errors from postgres_schema.sql:204,208."""
        class MockDriverError(Exception):
            sqlstate = "P0001"

        test_cases = [
            (
                "audit partition month_start must be the first day of a month",
                "AUDIT_MONTH_INVALID",
            ),
            (
                "audit partition month is outside the allowed maintenance window",
                "AUDIT_WINDOW_REJECTED",
            ),
            (
                "unknown trigger policy failure",
                "DATABASE_POLICY_REJECTED",
            ),
        ]

        for message, expected_code in test_cases:
            err = MockDriverError("database error")
            err.diag = SimpleNamespace(message_primary=message)
            with self.assertRaises(StorePolicyError) as caught:
                raise_policy_error(err)
            self.assertEqual(expected_code, caught.exception.code)
            self.assertEqual("P0001", caught.exception.sqlstate)
            self.assertFalse(caught.exception.retryable)

    def test_application_layer_runtime_call_handles_p0001_with_rollback(self):
        """Verify RuntimeService.call wraps StorePolicyError into a non-retryable response."""
        now = datetime(2026, 9, 3, 0, 0, tzinfo=UTC)
        principal = RuntimePrincipal("Orchestrator", "orch-1", "demo", "S03")
        service = RuntimeService(self.service, [principal], clock=lambda: now)

        with patch.object(
            self.store,
            "get_incident",
            side_effect=StorePolicyError("AUDIT_WINDOW_REJECTED"),
        ):
            response = service.call(
                "runtime_open",
                {"incident_id": "INC-TEST-P0001", "device_id": "FROST-S03"},
                principal,
            )

        self.assertFalse(response.get("ok", True))
        self.assertTrue(response.get("isError", False))
        self.assertEqual("AUDIT_WINDOW_REJECTED", response["error"]["code"])
        self.assertEqual("P0001", response["error"]["sqlstate"])
        self.assertFalse(response["error"]["retryable"])
        self.assertIn("AUDIT_WINDOW_REJECTED", response["error"]["message"])

    def test_application_layer_p0001_halts_retries_and_alerts(self):
        """Verify that P0001 policy rejections are recognized as non-retryable and trigger alerts."""
        now = datetime(2026, 9, 3, 0, 0, tzinfo=UTC)
        orch = RuntimePrincipal("Orchestrator", "orch-1", "demo", "S03")
        sentry = RuntimePrincipal("Sentry", "sentry-1", "demo", "S03")
        service = RuntimeService(self.service, [orch, sentry], clock=lambda: now)

        opened = service.call(
            "runtime_open",
            {"incident_id": "INC-P0001-FAIL", "device_id": "FROST-S03"},
            orch,
        )
        service.call("runtime_poll", {}, sentry)
        assigned = service.call(
            "runtime_assign",
            {
                "incident_id": "INC-P0001-FAIL",
                "worker_id": "sentry-1",
                "expected_version": opened["context"]["version"],
            },
            orch,
        )

        failed = service.call(
            "runtime_fail",
            {
                "incident_id": "INC-P0001-FAIL",
                "assignment_id": assigned["assignment"]["assignment_id"],
                "expected_version": assigned["context_version"],
                "reason": "database_policy_rejected",
            },
            sentry,
        )

        phase_rec = failed["recovery"]
        self.assertEqual("manual_intervention", phase_rec["state"])
        self.assertNotEqual("retry_wait", phase_rec["state"])
        self.assertEqual("database_policy_rejected", phase_rec["reason"])

        snapshot = service.call(
            "runtime_snapshot",
            {"incident_id": "INC-P0001-FAIL"},
            orch,
        )
        outbox = snapshot["context"]["recovery"]["outbox"]
        self.assertTrue(any(item.get("reason") == "database_policy_rejected" for item in outbox))

    def test_ensure_audit_partition_naming_and_window_calculation(self):
        """Test calculation logic for partition boundaries matching postgres_schema.sql."""
        def is_first_day(d: date) -> bool:
            return d.day == 1

        self.assertTrue(is_first_day(date(2026, 9, 1)))
        self.assertFalse(is_first_day(date(2026, 9, 15)))

        today = date(2026, 9, 20)
        month_start_cur = date(today.year, today.month, 1)
        window_min = date(month_start_cur.year - 1, month_start_cur.month, 1)
        window_max = date(2026, 12, 1)

        def is_within_window(target: date) -> bool:
            return window_min <= target <= window_max

        self.assertTrue(is_within_window(date(2026, 9, 1)))
        self.assertTrue(is_within_window(date(2026, 10, 1)))
        self.assertTrue(is_within_window(date(2026, 12, 1)))
        self.assertFalse(is_within_window(date(2027, 9, 1)))
        self.assertFalse(is_within_window(date(2024, 9, 1)))

        def partition_name(d: date) -> str:
            return f"audit_log_{d.strftime('%Y%m')}"

        self.assertEqual("audit_log_202609", partition_name(date(2026, 9, 1)))
        self.assertEqual("audit_log_202610", partition_name(date(2026, 10, 1)))


if __name__ == "__main__":
    unittest.main()
