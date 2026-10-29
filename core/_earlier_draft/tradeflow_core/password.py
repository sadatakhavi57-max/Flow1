"""Argon2id password hashing with the parameters pinned by contract section 3.

Implementation note: built on `cryptography` (RFC 9106 Argon2id) because `argon2-cffi` could not be installed
in the build environment. Hashes are standard PHC strings ($argon2id$v=19$m=..,t=..,p=..$salt$hash), i.e. fully
interchangeable with argon2-cffi, which the contract names for production. Swapping the backend later means
replacing `_derive` only; `tests/test_password.py` verifies the real seed hashes of migration 998.
"""
from __future__ import annotations

import base64
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

PLACEHOLDER_HASH = "TEMPORARY_PASSWORD_HASH"        # the old dev placeholder: never verifies


@dataclass(frozen=True)
class Argon2Params:
    time_cost: int = 3
    memory_cost: int = 65536                         # KiB
    parallelism: int = 4
    hash_len: int = 32
    salt_len: int = 16


DEFAULT_PARAMS = Argon2Params()


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4), validate=True)


def _derive(password: str, salt: bytes, t: int, m: int, p: int, length: int) -> bytes:
    return Argon2id(salt=salt, length=length, iterations=t, lanes=p, memory_cost=m).derive(password.encode("utf-8"))


def hash_password(password: str, params: Argon2Params = DEFAULT_PARAMS, *, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else os.urandom(params.salt_len)
    k = _derive(password, salt, params.time_cost, params.memory_cost, params.parallelism, params.hash_len)
    return f"$argon2id$v=19$m={params.memory_cost},t={params.time_cost},p={params.parallelism}${_b64e(salt)}${_b64e(k)}"


def _parse(phc: str):
    """-> (params, salt, hash) or None for anything that is not a well-formed argon2id v=19 PHC string."""
    try:
        empty, alg, ver, prm, salt, h = phc.split("$")
        if empty or alg != "argon2id" or ver != "v=19":
            return None
        kv = dict(x.split("=") for x in prm.split(","))
        if set(kv) != {"m", "t", "p"}:
            return None
        s, k = _b64d(salt), _b64d(h)
        return Argon2Params(int(kv["t"]), int(kv["m"]), int(kv["p"]), len(k), len(s)), s, k
    except (ValueError, TypeError):
        return None


def verify_password(password: str, stored: str | None) -> bool:
    """True only for a well-formed argon2id hash that matches. The dev placeholder and garbage return False."""
    if not stored or stored == PLACEHOLDER_HASH:
        return False
    parsed = _parse(stored)
    if parsed is None:
        return False
    p, salt, expected = parsed
    if p.memory_cost > 1 << 20 or p.time_cost > 10 or p.parallelism > 16:       # refuse absurd stored costs (DoS guard)
        return False
    return hmac.compare_digest(_derive(password, salt, p.time_cost, p.memory_cost, p.parallelism, p.hash_len), expected)


def needs_rehash(stored: str, params: Argon2Params = DEFAULT_PARAMS) -> bool:
    """Older parameters -> re-hash on the next successful login (section 3)."""
    parsed = _parse(stored)
    return parsed is None or parsed[0] != params


_DUMMY: str | None = None


def dummy_verify(password: str) -> None:
    """Burn the same work as a real verification when the user is unknown (comparable response time)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("tradeflow-dummy-password")
    verify_password(password, _DUMMY)
