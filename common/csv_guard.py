from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import errno
import os
import tempfile
import time


_LOCK_STALE_SEC = max(30, int(str(os.getenv("CSV_LOCK_STALE_SEC", "300")).strip() or "300"))


@contextmanager
def csv_file_lock(csv_path: str | Path, timeout_sec: float = 15.0, poll_sec: float = 0.05):
    """
    Cross-process lock based on sidecar .lock file.
    Avoids concurrent append/rewrite corruption on CSV files.
    """
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.with_suffix(p.suffix + ".lock")
    start = time.time()
    fd = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, f"pid={os.getpid()} ts={time.time():.3f}\n".encode("ascii", errors="ignore"))
            break
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            try:
                age = time.time() - float(lock_path.stat().st_mtime)
                if age >= float(_LOCK_STALE_SEC):
                    lock_path.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            if (time.time() - start) >= float(timeout_sec):
                raise TimeoutError(f"Timeout acquiring CSV lock: {lock_path}")
            time.sleep(float(poll_sec))
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def atomic_write_dataframe_csv(df, path: str | Path, *, index: bool = False, encoding: str = "utf-8", **kwargs):
    """
    Atomic CSV replacement: write temp file then os.replace.
    Call this while holding csv_file_lock(path).
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(str(tmp_path), index=index, encoding=encoding, **kwargs)
        try:
            with open(tmp_path, "rb") as f:
                os.fsync(f.fileno())
        except Exception:
            pass
        os.replace(str(tmp_path), str(target))
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
