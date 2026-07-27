from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentSafetyContractTests(unittest.TestCase):
    def test_automatic_real_assignment_changes_fail_closed(self):
        source = (ROOT / "webapp" / "app.py").read_text(encoding="utf-8")
        self.assertIn('desired_active = 0 if desired_mode == "real" else 1', source)
        self.assertIn('next_active = 0 if desired_mode == "real" else prev_active', source)
        self.assertIn("SET mode = ?, is_active = ?, updated_at = ?", source)

    def test_external_watchdog_requires_ok_and_recovers_mt5(self):
        source = (ROOT / "scripts" / "watch_webapp_health.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$Payload.status -eq "ok"', source)
        self.assertIn("function Ensure-Mt5Running", source)
        self.assertIn("Start-ScheduledTask -TaskName $Mt5TaskName", source)


if __name__ == "__main__":
    unittest.main()
