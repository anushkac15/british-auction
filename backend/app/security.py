"""Password hashing (scrypt) and signed bearer tokens (HMAC-SHA256), standard library only."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.config import settings

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(candidate, bytes.fromhex(digest))
    except ValueError:
        return False


# Compared against when the email is unknown, so both paths cost one scrypt call.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).digest())


def create_token(user_id: int) -> str:
    claims = {"sub": user_id, "exp": int(time.time()) + settings.token_ttl_minutes * 60}
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> int | None:
    """Returns the user id of a valid, unexpired token, else None."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int) or claims["exp"] <= time.time():
        return None
    user_id = claims.get("sub")
    return user_id if isinstance(user_id, int) else None
