from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
import re
import sys
from typing import BinaryIO, Iterator


class AlreadyRunningError(RuntimeError):
    """Raised when another process owns the requested instance lock."""


class SingleInstanceLock:
    """
    Cross-process, crash-safe instance lock.

    The lock file is intentionally retained for diagnostics. The operating system
    owns the actual byte-range lock and releases it automatically when the process
    exits, including an unhandled exception or a hard crash.
    """

    def __init__(self, name: str, lock_dir: str | Path | None = None):
        clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "").strip())
        if not clean_name:
            raise ValueError("Single-instance lock name cannot be empty")
        default_dir = Path(__file__).resolve().parents[1] / "runtime"
        self.path = Path(lock_dir) / f"{clean_name}.instance.lock" if lock_dir else default_dir / f"{clean_name}.instance.lock"
        self._file: BinaryIO | None = None
        self._locked = False

    def acquire(self) -> "SingleInstanceLock":
        if self._locked:
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(self.path, "a+b", buffering=0)
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
            lock_file.seek(0)
            self._lock_byte(lock_file)
        except OSError as exc:
            lock_file.close()
            raise AlreadyRunningError(
                f"Another '{self.path.stem}' process is already running (lock: {self.path})"
            ) from exc

        self._file = lock_file
        self._locked = True
        self._write_metadata()
        return self

    def _lock_byte(self, lock_file: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_byte(self, lock_file: BinaryIO) -> None:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _write_metadata(self) -> None:
        if self._file is None:
            return
        payload = {
            "pid": os.getpid(),
            "executable": sys.executable,
            "argv": sys.argv,
        }
        raw = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
        self._file.seek(0)
        self._file.truncate(0)
        self._file.write(raw)
        self._file.flush()

    def release(self) -> None:
        lock_file = self._file
        self._file = None
        if lock_file is None:
            self._locked = False
            return
        try:
            if self._locked:
                self._unlock_byte(lock_file)
        finally:
            self._locked = False
            lock_file.close()

    def __enter__(self) -> "SingleInstanceLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


@contextmanager
def single_instance(name: str, lock_dir: str | Path | None = None) -> Iterator[SingleInstanceLock]:
    lock = SingleInstanceLock(name, lock_dir=lock_dir)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()
