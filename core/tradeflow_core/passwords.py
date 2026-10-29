"""argon2id password hashing - contract section 3.

PHC string format (the same one argon2-cffi reads and writes): $argon2id$v=19$m=<KiB>,t=<iters>,p=<lanes>$<salt>$<hash>.
Implemented on `cryptography` (Argon2id, RFC 9106) because argon2-cffi could not be installed in the build environment;
when argon2-cffi is available the production wiring may use it - hashes are interchangeable (tests/test_passwords.py
documents the PHC layout).  Parameters are set explicitly here, never taken from a library default.
"""
from __future__ import annotations

import base64
import hmac
import os
import re
from dataclasses import dataclass

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


@dataclass(frozen=True)
class Argon2Params:
    time_cost: int = 3
    memory_cost: int = 65536      # KiB
    parallelism: int = 4
    hash_len: int = 32
    salt_len: int = 16


DEFAULT_PARAMS = Argon2Params()
MAX_PASSWORD_BYTES = 1024
# upper bounds applied to PARAMETERS READ FROM STORED HASHES, so a corrupted/hostile row cannot demand unbounded work
_MAX_M, _MAX_T, _MAX_P = 1 << 21, 10, 16
_PHC = re.compile(r"^\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)$")


def _b64(b: bytes) -> str:
    return base64.b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _derive(password: str, salt: bytes, t: int, m: int, p: int, n: int) -> bytes:
    return Argon2id(salt=salt, length=n, iterations=t, lanes=p, memory_cost=m).derive(password.encode("utf-8"))


def hash_password(password: str, params: Argon2Params = DEFAULT_PARAMS, *, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or not password or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("password must be 1..1024 bytes")
    salt = salt if salt is not None else os.urandom(params.salt_len)
    k = _derive(password, salt, params.time_cost, params.memory_cost, params.parallelism, params.hash_len)
    return f"$argon2id$v=19$m={params.memory_cost},t={params.time_cost},p={params.parallelism}${_b64(salt)}${_b64(k)}"


def _parse(phc: str):
    m = _PHC.match(phc or "")
    if not m:
        return None
    mem, t, p = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (8 * p <= mem <= _MAX_M and 1 <= t <= _MAX_T and 1 <= p <= _MAX_P):
        return None
    salt, h = _unb64(m.group(4)), _unb64(m.group(5))
    if len(salt) < 8 or len(h) < 16:
        return None
    return mem, t, p, salt, h


def verify_password(password: str, phc: str) -> bool:
    """False for anything that is not a well-formed argon2id hash (including the dev placeholder TEMPORARY_PASSWORD_HASH)."""
    try:
        parsed = _parse(phc)
        if parsed is None or not isinstance(password, str) or not password or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            return False
        mem, t, p, salt, h = parsed
        return hmac.compare_digest(_derive(password, salt, t, mem, p, len(h)), h)
    except Exception:
        return False


def needs_rehash(phc: str, params: Argon2Params = DEFAULT_PARAMS) -> bool:
    parsed = _parse(phc)
    if parsed is None:
        return True
    mem, t, p, salt, h = parsed
    return (mem, t, p, len(h)) != (params.memory_cost, params.time_cost, params.parallelism, params.hash_len)


_dummy: str | None = None


def verify_or_dummy(password: str, phc: str | None) -> bool:
    """Login helper: when the user does not exist, still spend one hash computation so timing does not reveal it."""
    global _dummy
    if phc is None:
        if _dummy is None:
            _dummy = hash_password("dummy-password-for-timing")
        verify_password(password, _dummy)
        return False
    return verify_password(password, phc)
