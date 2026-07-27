from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from common.single_instance import AlreadyRunningError, SingleInstanceLock


class SingleInstanceTests(unittest.TestCase):
    def test_second_owner_is_rejected_and_release_allows_reacquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = SingleInstanceLock("worker", lock_dir=tmp)
            second = SingleInstanceLock("worker", lock_dir=tmp)
            first.acquire()
            try:
                with self.assertRaises(AlreadyRunningError):
                    second.acquire()
            finally:
                first.release()

            replacement = SingleInstanceLock("worker", lock_dir=tmp)
            replacement.acquire()
            replacement.release()
            self.assertTrue((Path(tmp) / "worker.instance.lock").exists())

    def test_context_manager_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with SingleInstanceLock("worker", lock_dir=tmp):
                    raise RuntimeError("boom")

            with SingleInstanceLock("worker", lock_dir=tmp):
                pass


if __name__ == "__main__":
    unittest.main()
