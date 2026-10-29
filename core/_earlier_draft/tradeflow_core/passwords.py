"""Password hashing - contract section 3: argon2id, parameters set explicitly in configuration.

Production uses `argon2-cffi` (pinned in the lock file). When it is not importable (this core is developed in an
environment where it cannot be installed) the same PHC-format hash is produced/verified with `cryptography`'s Argon2id;
both implement RFC 9106 argon2id v=19, so hashes are interchangeable (tested here against the cryptography path only -
interchangeability with argon2-cffi is an integration test, see INTEGRATION_TODO.md).
"""
from __future__ import annotations

import base64
import hmac
import os
import re
from dataclasses import dataclass

try:                                               # production path
    from argon2.low_level import Type, hash_secret_raw as _raw_cffi
    _BACKEND = "argon2-cffi"
except Exception:                                  # development / test path
    _raw_cffi = None
    _BACKEND = "cryptography"
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id as _Argon2id

PLACEHOLDER = "TEMPORARY_PASSWORD_HASH"            # dev seed placeholder: never verifies


@dataclass(frozen=True)
class Argon2Params:
    time_cost: int = 3
    memory_cost: int = 65536          # KiB
    parallelism: int = 4
    hash_len: int = 32
    salt_len: int = 16


DEFAULT_PARAMS = Argon2Params()
_PHC = re.compile(r"^\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)$")


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _derive(pw: bytes, salt: bytes, t: int, m: int, p: int, n: int) -> bytes:
    if _raw_cffi is not None:
        return _raw_cffi(secret=pw, salt=salt, time_cost=t, memory_cost=m, parallelism=p, hash_len=n, type=Type.ID, version=19)
    return _Argon2id(salt=salt, length=n, iterations=t, lanes=p, memory_cost=m).derive(pw)


def backend() -> str:
    return _BACKEND


def hash_password(password: str, params: Argon2Params = DEFAULT_PARAMS, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else os.urandom(params.salt_len)
    k = _derive(password.encode(), salt, params.time_cost, params.memory_cost, params.parallelism, params.hash_len)
    return f"$argon2id$v=19$m={params.memory_cost},t={params.time_cost},p={params.parallelism}${_b64e(salt)}${_b64e(k)}"


def verify_password(password: str, stored: str | None) -> bool:
    """False for the dev placeholder, for anything that is not a well-formed argon2id v19 hash, and for a wrong password."""
    if not stored or stored == PLACEHOLDER:
        return False
    m = _PHC.match(stored)
    if not m:
        return False
    mem, t, p, salt, digest = int(m[1]), int(m[2]), int(m[3]), _b64d(m[4]), _b64d(m[5])
    if not (8 <= mem <= 4 * 1024 * 1024 and 1 <= t <= 100 and 1 <= p <= 64 and 4 <= len(digest) <= 128 and len(salt) >= 8):
        return False                                 # refuse absurd parameters from a corrupted/hostile row
    k = _derive(password.encode(), salt, t, mem, p, len(digest))
    return hmac.compare_digest(k, digest)


def needs_rehash(stored: str, params: Argon2Params = DEFAULT_PARAMS) -> bool:
    m = _PHC.match(stored or "")
    if not m:
        return True
    return (int(m[1]), int(m[2]), int(m[3]), len(_b64d(m[5]))) != (params.memory_cost, params.time_cost, params.parallelism, params.hash_len)


_DUMMY = None


def dummy_verify(password: str, params: Argon2Params = DEFAULT_PARAMS) -> None:
    """Burn the same work as a real verification (unknown organization/user) so timing does not reveal existence."""
    global _DUMMY
    if _DUMMY is None or needs_rehash(_DUMMY, params):
        _DUMMY = hash_password("dummy-password-for-timing", params)
    verify_password(password, _DUMMY)
