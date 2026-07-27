from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from common.execution_safety import (
    ExecutionSafetyError,
    ensure_execution_allowed,
    evaluate_entry_freshness,
    validate_account_policy,
)


class ExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.demo = SimpleNamespace(trade_mode=0, login=123, server="Broker-Demo")
        self.live = SimpleNamespace(trade_mode=2, login=456, server="Broker-Real")

    def test_execution_is_disarmed_by_policy(self):
        with self.assertRaisesRegex(ExecutionSafetyError, "TRADING_BOT_EXECUTION_ARMED"):
            ensure_execution_allowed(
                armed=False,
                account_info=self.demo,
                require_demo=True,
                demo_trade_mode=0,
            )

    def test_armed_demo_account_is_allowed(self):
        ensure_execution_allowed(
            armed=True,
            account_info=self.demo,
            require_demo=True,
            demo_trade_mode=0,
        )

    def test_live_account_is_rejected_by_default(self):
        with self.assertRaisesRegex(ExecutionSafetyError, "demo account required"):
            validate_account_policy(self.live, require_demo=True, demo_trade_mode=0)

    def test_live_account_requires_explicit_demo_override(self):
        validate_account_policy(self.live, require_demo=False, demo_trade_mode=0)

    def test_recent_entry_is_allowed(self):
        now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
        result = evaluate_entry_freshness(
            (now - timedelta(seconds=299)).isoformat(),
            ttl_seconds=300,
            now=now,
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "fresh")

    def test_stale_entry_is_blocked(self):
        now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
        result = evaluate_entry_freshness(
            (now - timedelta(seconds=301)).isoformat(),
            ttl_seconds=300,
            now=now,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "entry_event_expired")
        self.assertEqual(result.age_seconds, 301.0)

    def test_missing_or_invalid_entry_timestamp_fails_closed(self):
        missing = evaluate_entry_freshness("", ttl_seconds=300)
        invalid = evaluate_entry_freshness("not-a-date", ttl_seconds=300)
        self.assertEqual(missing.reason, "entry_timestamp_missing")
        self.assertEqual(invalid.reason, "entry_timestamp_invalid")
        self.assertFalse(missing.allowed)
        self.assertFalse(invalid.allowed)


if __name__ == "__main__":
    unittest.main()
