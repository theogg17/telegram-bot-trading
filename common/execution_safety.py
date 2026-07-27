from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class ExecutionSafetyError(RuntimeError):
    """Raised when an MT5 write is blocked by the configured safety policy."""


@dataclass(frozen=True)
class EntryFreshness:
    allowed: bool
    age_seconds: float | None
    reason: str


def validate_account_policy(
    account_info: Any,
    *,
    require_demo: bool,
    demo_trade_mode: int = 0,
) -> None:
    """Fail closed when demo-only mode is enabled and MT5 is not a demo account."""
    if account_info is None:
        raise ExecutionSafetyError("MT5 account information is unavailable")
    if not require_demo:
        return
    trade_mode = getattr(account_info, "trade_mode", None)
    if trade_mode is None or int(trade_mode) != int(demo_trade_mode):
        login = getattr(account_info, "login", "unknown")
        server = getattr(account_info, "server", "unknown")
        raise ExecutionSafetyError(
            "MT5 demo account required by TRADING_BOT_REQUIRE_DEMO_ACCOUNT "
            f"(login={login}, server={server}, trade_mode={trade_mode})"
        )


def ensure_execution_allowed(
    *,
    armed: bool,
    account_info: Any,
    require_demo: bool,
    demo_trade_mode: int = 0,
) -> None:
    """Require both the explicit arm switch and an account allowed by policy."""
    if not armed:
        raise ExecutionSafetyError(
            "MT5 writes are disabled; set TRADING_BOT_EXECUTION_ARMED=true explicitly to enable them"
        )
    validate_account_policy(
        account_info,
        require_demo=require_demo,
        demo_trade_mode=demo_trade_mode,
    )


def evaluate_entry_freshness(
    timestamp_value: Any,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> EntryFreshness:
    """
    Decide whether a newly processed entry is recent enough for an MT5 write.

    Missing or malformed timestamps fail closed. Naive timestamps are interpreted
    in the timezone supplied by ``now`` (the daemon passes its Uruguay timezone).
    """
    ttl = int(ttl_seconds)
    if ttl <= 0:
        raise ValueError("ttl_seconds must be greater than zero")

    text = str(timestamp_value or "").strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return EntryFreshness(False, None, "entry_timestamp_missing")
    try:
        event_time = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return EntryFreshness(False, None, "entry_timestamp_invalid")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=current.tzinfo)
    age = max(0.0, (current.astimezone(timezone.utc) - event_time.astimezone(timezone.utc)).total_seconds())
    if age > ttl:
        return EntryFreshness(False, age, "entry_event_expired")
    return EntryFreshness(True, age, "fresh")
