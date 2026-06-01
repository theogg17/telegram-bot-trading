import asyncio
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)


BASE_DIR = Path(__file__).resolve().parent
SESSION_BASENAME = BASE_DIR / "session_name"
SESSION_FILE = BASE_DIR / "session_name.session"


class TelegramAuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def session_exists() -> bool:
    return SESSION_FILE.exists()


def delete_session() -> None:
    for path in BASE_DIR.glob("session_name.session*"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _clean_api_id(value) -> int:
    try:
        api_id = int(value)
    except Exception as exc:
        raise TelegramAuthError("invalid_api_id", "Telegram API ID debe ser numerico.") from exc
    if api_id <= 0:
        raise TelegramAuthError("invalid_api_id", "Telegram API ID debe ser mayor a cero.")
    return api_id


def _clean_required(value: str, code: str, label: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise TelegramAuthError(code, f"{label} es obligatorio.")
    return clean


def _client(api_id: int, api_hash: str) -> TelegramClient:
    return TelegramClient(str(SESSION_BASENAME), api_id, api_hash)


async def _send_code_async(api_id, api_hash, phone) -> dict:
    clean_api_id = _clean_api_id(api_id)
    clean_hash = _clean_required(api_hash, "missing_api_hash", "Telegram API Hash")
    clean_phone = _clean_required(phone, "missing_phone", "Telefono")
    client = _client(clean_api_id, clean_hash)
    try:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            return {
                "status": "already_authorized",
                "session_exists": True,
                "user": getattr(me, "username", "") or getattr(me, "first_name", "") or "",
            }
        sent = await client.send_code_request(clean_phone)
        return {
            "status": "code_sent",
            "phone_code_hash": sent.phone_code_hash,
            "phone": clean_phone,
            "session_exists": session_exists(),
        }
    except ApiIdInvalidError as exc:
        raise TelegramAuthError("invalid_api_credentials", "API ID/API Hash invalidos.") from exc
    except FloodWaitError as exc:
        raise TelegramAuthError("flood_wait", f"Telegram pidio esperar {int(exc.seconds)} segundos antes de reintentar.") from exc
    except PhoneNumberInvalidError as exc:
        raise TelegramAuthError("invalid_phone", "Telefono invalido. Usa formato internacional, por ejemplo +598...") from exc
    finally:
        await client.disconnect()


async def _confirm_code_async(api_id, api_hash, phone, code, phone_code_hash) -> dict:
    clean_api_id = _clean_api_id(api_id)
    clean_hash = _clean_required(api_hash, "missing_api_hash", "Telegram API Hash")
    clean_phone = _clean_required(phone, "missing_phone", "Telefono")
    clean_code = _clean_required(code, "missing_code", "Codigo")
    clean_hash_code = _clean_required(phone_code_hash, "missing_phone_code_hash", "Token de codigo")
    client = _client(clean_api_id, clean_hash)
    try:
        await client.connect()
        await client.sign_in(clean_phone, clean_code, phone_code_hash=clean_hash_code)
        me = await client.get_me()
        return {
            "status": "authorized",
            "needs_password": False,
            "session_exists": session_exists(),
            "user": getattr(me, "username", "") or getattr(me, "first_name", "") or "",
        }
    except SessionPasswordNeededError:
        return {"status": "password_required", "needs_password": True, "session_exists": session_exists()}
    except PhoneCodeInvalidError as exc:
        raise TelegramAuthError("invalid_code", "Codigo de Telegram invalido.") from exc
    except PhoneCodeExpiredError as exc:
        raise TelegramAuthError("expired_code", "El codigo expiro. Envia un codigo nuevo.") from exc
    except FloodWaitError as exc:
        raise TelegramAuthError("flood_wait", f"Telegram pidio esperar {int(exc.seconds)} segundos antes de reintentar.") from exc
    finally:
        await client.disconnect()


async def _confirm_password_async(api_id, api_hash, password) -> dict:
    clean_api_id = _clean_api_id(api_id)
    clean_hash = _clean_required(api_hash, "missing_api_hash", "Telegram API Hash")
    clean_password = _clean_required(password, "missing_password", "Password 2FA")
    client = _client(clean_api_id, clean_hash)
    try:
        await client.connect()
        await client.sign_in(password=clean_password)
        me = await client.get_me()
        return {
            "status": "authorized",
            "needs_password": False,
            "session_exists": session_exists(),
            "user": getattr(me, "username", "") or getattr(me, "first_name", "") or "",
        }
    except PasswordHashInvalidError as exc:
        raise TelegramAuthError("invalid_password", "Password 2FA incorrecto.") from exc
    except FloodWaitError as exc:
        raise TelegramAuthError("flood_wait", f"Telegram pidio esperar {int(exc.seconds)} segundos antes de reintentar.") from exc
    finally:
        await client.disconnect()


async def _check_session_async(api_id=None, api_hash=None) -> dict:
    exists = session_exists()
    if not exists or not api_id or not api_hash:
        return {"session_exists": exists, "authorized": None, "user": ""}
    client = _client(_clean_api_id(api_id), str(api_hash).strip())
    try:
        await client.connect()
        authorized = bool(await client.is_user_authorized())
        user = ""
        if authorized:
            me = await client.get_me()
            user = getattr(me, "username", "") or getattr(me, "first_name", "") or ""
        return {"session_exists": exists, "authorized": authorized, "user": user}
    finally:
        await client.disconnect()


def _run(coro):
    return asyncio.run(coro)


def send_code(api_id, api_hash, phone) -> dict:
    return _run(_send_code_async(api_id, api_hash, phone))


def confirm_code(api_id, api_hash, phone, code, phone_code_hash) -> dict:
    return _run(_confirm_code_async(api_id, api_hash, phone, code, phone_code_hash))


def confirm_password(api_id, api_hash, password) -> dict:
    return _run(_confirm_password_async(api_id, api_hash, password))


def check_session(api_id=None, api_hash=None) -> dict:
    return _run(_check_session_async(api_id, api_hash))
