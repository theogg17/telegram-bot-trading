# Lector/message_parser_chatgpt.py
import csv
import json
import os
import re
import time

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, SIGNALS_CSV

SYSTEM_PROMPT = (
    "You are a trading signal parser. Return ONLY valid JSON with this exact top-level shape:\n"
    "{\n"
    '  "symbol": "unknown",\n'
    '  "operation": "BUY" | "SELL" | "unknown",\n'
    '  "events": [ ... ]\n'
    "}\n"
    "Rules:\n"
    "- Parse ALL actionable instructions in the message into SEPARATE events inside the array.\n"
    "- Each event has 'type' ∈ {entry, modification, close} and optional fields:\n"
    "  entry: entry_price, stop_loss, take_profit, operator_class (SCALP|SWING)\n"
    "  modification: operator_class, new_stop_loss, new_take_profit, move_to_breakeven (true/false)\n"
    "  close: operator_class, close_pnl_pips (number if present), close_reason\n"
    "- If the message contains an entry with SL/TP and NO modification/close instructions, "
    "  the array MUST contain exactly ONE event of type 'entry' (operator_class=SWING unless specified).\n"
    "- If message says to move/set SL or TP, return a 'modification' event with new_stop_loss/new_take_profit.\n"
    "- If message says TP hit / SL hit / stop hit, return a 'close' event with close_reason.\n"
    "- If message explicitly contains a tradable symbol (example EURUSD/XAUUSD/BTCUSD), top-level symbol MUST match it.\n"
    "- If message explicitly contains BUY or SELL, top-level operation MUST match it.\n"
    "- Use operator_class SWING when not specified.\n"
    "- Omit unknown fields. Do not output any text outside JSON."
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        idx = text.find("{")
        text = text[idx:]
    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1 or end <= 0:
        raise ValueError("No JSON found in model output")
    return json.loads(text[start:end])


def _coerce_events(obj: dict) -> list:
    events = obj.get("events", [])
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def _normalize_operator_class_value(value: str, ev_type: str) -> str:
    code = str(value or "").strip().upper()
    if code == "STANDARD":
        code = "SWING"
    if code not in ("SCALP", "SWING"):
        return "SWING" if str(ev_type).lower() == "entry" else ""
    return code


# --- Heurísticas sobre el TEXTO ---
_ENTRY_HINT = re.compile(r"\bENTRY\b|\bENTRY PRICE\b|^ENTRY[: ]", re.I)
_SL_HINT = re.compile(r"\bSL\b|STOP", re.I)
_TP_HINT = re.compile(r"\bTP\b|TAKE\s*PROFIT", re.I)
_CLOSE_HINT = re.compile(r"\bCLOSE\b", re.I)
_PIPS_HINT = re.compile(r"\+\s*\d+\s*PIPS", re.I)
_TP_HIT = re.compile(r"\bTP\b\s*(HIT|HITTED|REACHED|TARGET)\b|\bTAKE\s*PROFIT\s*(HIT|HITTED|REACHED)\b", re.I)
_SL_HIT = re.compile(r"\bSL\b\s*(HIT|HITTED|REACHED|TRIGGERED)\b|\bSTOP\s*(HIT|HITTED|OUT|TRIGGERED)\b", re.I)
_MOVE_BE = re.compile(r"(MOVE|SET|ADJUST|MODIFY|CHANGE)\s*SL\s*(TO|=|:)?\s*(BREAKEVEN|B/?E|BE)", re.I)
_MOVE_SL_TO_PRICE = re.compile(r"(MOVE|SET|ADJUST|MODIFY|CHANGE)\s*SL\s*(TO|=|:)?\s*([0-9][0-9\s\.,]{2,})", re.I)
_SL_TO_PRICE = re.compile(r"\bSL\b\s*(TO|=|:)?\s*([0-9][0-9\s\.,]{2,})", re.I)
_TP_TO_PRICE = re.compile(r"\bTP\b\s*(TO|=|:)?\s*([0-9][0-9\s\.,]{2,})", re.I)
_MODIFY_HINT = re.compile(r"(MOVE|SET|ADJUST|MODIFY|CHANGE)\s*(SL|TP)\b", re.I)
_SWING_WORD = re.compile(r"\bSWING\b", re.I)
_SCALP_WORD = re.compile(r"\bSCALP\b", re.I)

_FX_CODES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "XAU", "XAG", "BTC", "ETH",
}
_SYMBOL_SLASH = re.compile(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", re.I)
_SYMBOL_TOKEN = re.compile(r"\b([A-Z]{6,7})\b", re.I)
_SIDE_TOKEN = re.compile(r"\b(BUY|SELL)\b", re.I)


def _symbol_from_text(message_text: str):
    text = str(message_text or "").upper()
    for m in _SYMBOL_SLASH.finditer(text):
        cand = f"{m.group(1)}{m.group(2)}"
        if cand[:3] in _FX_CODES and cand[3:] in _FX_CODES:
            return cand
    for m in _SYMBOL_TOKEN.finditer(text):
        cand = str(m.group(1) or "").upper()
        if cand == "BTCUSDT":
            return cand
        if len(cand) == 6 and cand[:3] in _FX_CODES and cand[3:] in _FX_CODES:
            return cand
    return None


def _side_from_text(message_text: str):
    m = _SIDE_TOKEN.search(str(message_text or "").upper())
    if not m:
        return None
    return str(m.group(1)).upper()


def _enforce_symbol_side_from_text(message_text: str, symbol, operation, events: list):
    sym_hint = _symbol_from_text(message_text)
    side_hint = _side_from_text(message_text)
    sym = str(symbol or "unknown").strip().upper() or "unknown"
    side = str(operation or "unknown").strip().upper() or "unknown"

    if sym_hint:
        sym = sym_hint
    if side_hint:
        side = side_hint

    fixed = []
    for e in events:
        ee = dict(e)
        et = str(ee.get("type") or "").lower()
        if et == "entry":
            if sym_hint:
                ee["symbol"] = sym_hint
            else:
                ee.setdefault("symbol", sym)
            if side_hint:
                ee["operation"] = side_hint
            else:
                ee.setdefault("operation", side)
        else:
            ee.setdefault("symbol", sym)
            ee.setdefault("operation", side)
        fixed.append(ee)
    return sym, side, fixed


def _infer_extra_events_from_text(message_text: str, events: list) -> list:
    text = message_text
    events = events[:]  # copia

    has_mod_any = any(e.get("type") == "modification" for e in events)
    has_close_any = any(e.get("type") == "close" for e in events)
    has_scalp_close = any(
        e.get("type") == "close" and str(e.get("operator_class", "")).upper() == "SCALP"
        for e in events
    )
    has_swing_mod = any(
        e.get("type") == "modification" and str(e.get("operator_class", "")).upper() == "SWING"
        for e in events
    )

    # SCALP CLOSE + PIPS
    if not has_scalp_close and _SCALP_WORD.search(text) and (_CLOSE_HINT.search(text) or _PIPS_HINT.search(text)):
        m = _PIPS_HINT.search(text)
        pnl = int(m.group(0).replace("+", "").replace("PIPS", "").strip()) if m else None
        ev = {"type": "close", "operator_class": "SCALP"}
        if pnl is not None:
            ev["close_pnl_pips"] = pnl
            ev["close_reason"] = f"+{pnl} pips"
        events.append(ev)

    # TP/SL HIT => CLOSE
    if not has_close_any and (_TP_HIT.search(text) or _SL_HIT.search(text)):
        operator_class = "SWING"
        if _SWING_WORD.search(text):
            operator_class = "SWING"
        elif _SCALP_WORD.search(text):
            operator_class = "SCALP"
        reason = "tp hit" if _TP_HIT.search(text) else "sl hit"
        events.append(
            {
                "type": "close",
                "operator_class": operator_class,
                "close_reason": reason,
            }
        )
        has_close_any = True

    # move SL to BE (generic or SWING)
    if _MOVE_BE.search(text) and not has_swing_mod:
        operator_class = "SWING"
        if _SWING_WORD.search(text):
            operator_class = "SWING"
        elif _SCALP_WORD.search(text):
            operator_class = "SCALP"
        events.append(
            {
                "type": "modification",
                "operator_class": operator_class,
                "move_to_breakeven": True,
                "new_stop_loss": "breakeven",
            }
        )
        has_mod_any = True

    # move SL to explicit price
    if not has_mod_any:
        m = _MOVE_SL_TO_PRICE.search(text)
        if m:
            price = _parse_price(m.group(3))
            if price is not None:
                operator_class = "SWING"
                if _SWING_WORD.search(text):
                    operator_class = "SWING"
                elif _SCALP_WORD.search(text):
                    operator_class = "SCALP"
                events.append(
                    {
                        "type": "modification",
                        "operator_class": operator_class,
                        "new_stop_loss": price,
                    }
                )

    return events


def _enforce_entry_only_when_appropriate(message_text: str, reply_to_msg_id, events: list) -> list:
    text = message_text
    is_entryish = bool(_ENTRY_HINT.search(text) or (_SL_HINT.search(text) and _TP_HINT.search(text)))
    has_modify = bool(_MOVE_BE.search(text) or _MODIFY_HINT.search(text) or _MOVE_SL_TO_PRICE.search(text))
    has_close = bool(_CLOSE_HINT.search(text) or _PIPS_HINT.search(text) or _TP_HIT.search(text) or _SL_HIT.search(text))

    if reply_to_msg_id is None and is_entryish and not (has_modify or has_close):
        # Quedate SOLO con 'entry'
        only_entries = [e for e in events if e.get("type") == "entry"]
        if not only_entries:
            only_entries = [{"type": "entry"}]
        for e in only_entries:
            if not e.get("operator_class"):
                if _SCALP_WORD.search(text):
                    e["operator_class"] = "SCALP"
                elif _SWING_WORD.search(text):
                    e["operator_class"] = "SWING"
                else:
                    e["operator_class"] = "SWING"
        return only_entries

    # Si no es entry puro: borra 'modification' si no hay evidencia textual (solo cuando no es reply)
    cleaned = []
    for e in events:
        if reply_to_msg_id is None and e.get("type") == "modification" and not has_modify:
            continue
        cleaned.append(e)

    # Normaliza operator_class en entries si no está claro
    for e in cleaned:
        if e.get("type") == "entry" and not e.get("operator_class"):
            if _SCALP_WORD.search(text):
                e["operator_class"] = "SCALP"
            elif _SWING_WORD.search(text):
                e["operator_class"] = "SWING"
            else:
                e["operator_class"] = "SWING"

    return cleaned


# ===== Busca el entry original en signals.csv y retorna symbol/operation =====

def _lookup_previous_signal(reply_to_msg_id: int):
    if not reply_to_msg_id:
        return None
    path = SIGNALS_CSV
    if not os.path.exists(path):
        return None

    found = None
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = str(row.get("message_id", "")).strip()
                if mid and mid == str(reply_to_msg_id):
                    found = {
                        "symbol": (row.get("symbol") or "").strip(),
                        "operation": (row.get("operation") or "").strip(),
                        "type": (row.get("type") or "").strip(),
                    }
    except Exception:
        return None
    return found


def _inherit_symbol_operation_if_reply(symbol, operation, events, reply_to_msg_id):
    prev = _lookup_previous_signal(reply_to_msg_id)
    if not prev:
        return symbol, operation, events

    sym = symbol or ""
    op = operation or ""
    prev_sym = (prev.get("symbol") or "").strip()
    prev_op = (prev.get("operation") or "").strip()

    has_close_mod = any(e.get("type") in ("close", "modification") for e in events)
    if has_close_mod:
        if prev_sym:
            sym = prev_sym
        if prev_op:
            op = prev_op
    else:
        if sym.lower() in ("", "unknown") and prev_sym:
            sym = prev_sym
        if op.lower() in ("", "unknown") and prev_op:
            op = prev_op

    fixed_events = []
    for e in events:
        ee = dict(e)
        if ee.get("type") in ("close", "modification"):
            # For replies, always prefer the original entry symbol/operation.
            if prev_sym:
                ee["symbol"] = prev_sym
            else:
                ee.setdefault("symbol", sym)
            if prev_op:
                ee["operation"] = prev_op
            else:
                ee.setdefault("operation", op)
        fixed_events.append(ee)

    return sym, op, fixed_events


# ===== NUEVO: Fallback “close now” en replies cortos =====

def _force_close_on_short_reply(message_text: str, reply_to_msg_id, symbol: str, operation: str, events: list):
    """
    Si es reply, el texto contiene 'close' y NO hay ningún 'close' en events,
    forzar un evento de cierre SIN operator_class (=> Operador cierra TODO).
    """
    if not reply_to_msg_id:
        return events
    if not (_CLOSE_HINT.search(message_text) or _TP_HIT.search(message_text) or _SL_HIT.search(message_text)):
        return events
    has_close = any(e.get("type") == "close" for e in events)
    if has_close:
        return events

    ev = {
        "type": "close",
        # OJO: NO ponemos operator_class aquí
        "close_reason": "now",
        "symbol": symbol,
        "operation": operation,
    }
    return events + [ev]


def _parse_price(raw: str):
    if not raw:
        return None
    cleaned = raw.replace(" ", "").replace(",", ".")
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = parts[0] + "." + "".join(parts[1:])
    try:
        return float(cleaned)
    except Exception:
        return None


def _infer_modification_from_reply(message_text: str, reply_to_msg_id, events: list) -> list:
    if not reply_to_msg_id:
        return events
    if any(e.get("type") == "modification" for e in events):
        return events

    text = message_text
    operator_class = "SWING"
    if _SWING_WORD.search(text):
        operator_class = "SWING"
    elif _SCALP_WORD.search(text):
        operator_class = "SCALP"

    # breakeven hints in reply
    if _MOVE_BE.search(text) or (_SL_HINT.search(text) and re.search(r"\b(BREAKEVEN|B/?E|BE)\b", text, re.I)):
        return events + [{
            "type": "modification",
            "operator_class": operator_class,
            "move_to_breakeven": True,
            "new_stop_loss": "breakeven",
        }]

    m = _MOVE_SL_TO_PRICE.search(text) or _SL_TO_PRICE.search(text)
    if m:
        price = _parse_price(m.group(3) if m.re is _MOVE_SL_TO_PRICE else m.group(2))
        if price is not None:
            return events + [{
                "type": "modification",
                "operator_class": operator_class,
                "new_stop_loss": price,
            }]

    m = _TP_TO_PRICE.search(text)
    if m:
        price = _parse_price(m.group(2))
        if price is not None:
            return events + [{
                "type": "modification",
                "operator_class": operator_class,
                "new_take_profit": price,
            }]

    return events


# ================================================================


def _build_client():
    if OPENAI_BASE_URL:
        return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return OpenAI(api_key=OPENAI_API_KEY)


def parse_signal_chatgpt(message, timestamp, msg_id, reply_to_msg_id, channel_name):
    try:
        client = _build_client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Message: {message}"},
        ]

        last_error = None
        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    temperature=0,
                    timeout=25,
                )
                content = response.choices[0].message.content
                obj = _extract_json(content)
                break
            except Exception as e:
                last_error = e
                time.sleep(0.5)
        else:
            raise last_error

        symbol = obj.get("symbol", "unknown")
        operation = obj.get("operation", "unknown")
        events = _coerce_events(obj)

        # Soporte a modelos que devuelven un único objeto plano
        if not events and obj.get("type"):
            ev = {k: v for k, v in obj.items() if k not in ("symbol", "operation")}
            events = [ev]

        # Post-procesado determinista
        events = _infer_extra_events_from_text(message, events)
        events = _infer_modification_from_reply(message, reply_to_msg_id, events)
        events = _enforce_entry_only_when_appropriate(message, reply_to_msg_id, events)
        symbol, operation, events = _enforce_symbol_side_from_text(message, symbol, operation, events)

        # Heredar symbol/operation si es reply
        symbol, operation, events = _inherit_symbol_operation_if_reply(
            symbol, operation, events, reply_to_msg_id
        )

        # Fallback: reply corto con "close" => forzar close general now
        events = _force_close_on_short_reply(message, reply_to_msg_id, symbol, operation, events)

        normalized_events = []
        for ev in events:
            out_ev = dict(ev)
            et = str(out_ev.get("type") or "").lower()
            out_ev["operator_class"] = _normalize_operator_class_value(out_ev.get("operator_class", ""), et)
            normalized_events.append(out_ev)

        return {"symbol": symbol, "operation": operation, "events": normalized_events}

    except Exception as e:
        print(f"Error parsing with ChatGPT: {e}")
        return None
