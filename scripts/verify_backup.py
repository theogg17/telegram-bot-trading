from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile


REQUIRED_ENTRIES = {
    "metadata/backup_metadata.json",
    "config/trading_bot.db",
}


def verify_backup(path: Path) -> dict:
    result: dict[str, object] = {
        "ok": False,
        "path": str(path),
        "size_bytes": 0,
        "sha256": "",
        "zip_crc": False,
        "db_integrity": "",
        "error": "",
    }
    try:
        if not path.is_file():
            raise FileNotFoundError(f"backup not found: {path}")
        result["size_bytes"] = path.stat().st_size

        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result["sha256"] = digest.hexdigest()

        with zipfile.ZipFile(path, "r") as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise RuntimeError(f"ZIP CRC failed: {bad_member}")
            result["zip_crc"] = True
            names = set(archive.namelist())
            missing = sorted(REQUIRED_ENTRIES - names)
            if missing:
                raise RuntimeError(f"required entries missing: {missing}")
            metadata = json.loads(archive.read("metadata/backup_metadata.json").decode("utf-8"))
            if not bool(metadata.get("db_snapshot")):
                raise RuntimeError("backup metadata reports db_snapshot=false")
            with tempfile.TemporaryDirectory(prefix="tradingbot-backup-check-") as tmp:
                db_path = Path(tmp) / "trading_bot.db"
                db_path.write_bytes(archive.read("config/trading_bot.db"))
                connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
                try:
                    row = connection.execute("PRAGMA integrity_check").fetchone()
                finally:
                    connection.close()
                integrity = str(row[0] if row else "")
                result["db_integrity"] = integrity
                if integrity.lower() != "ok":
                    raise RuntimeError(f"SQLite integrity_check failed: {integrity}")

        result["ok"] = True
    except Exception as exc:  # a diagnostic must return structured failure
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a TradingBot backup ZIP and its SQLite snapshot.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = verify_backup(args.path.resolve())
    if args.as_json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        for key, value in result.items():
            print(f"{key}={value}")
    return 0 if bool(result["ok"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
