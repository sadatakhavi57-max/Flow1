"""Settings validation (pure; reads a mapping, not the process environment, so it is testable)."""
from __future__ import annotations

from dataclasses import dataclass


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    access_ttl_seconds: int = 3600
    refresh_ttl_days: int = 30
    refresh_grace_seconds: int = 10
    workers: int = 1
    environment: str = "development"


def load(env: dict) -> tuple[Settings, list[str]]:
    """-> (settings, warnings). Raises ConfigError listing every problem. The in-process login limiter requires WORKERS=1."""
    errs, warns = [], []
    secret = env.get("TRADEFLOW_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        errs.append("TRADEFLOW_JWT_SECRET must be at least 32 bytes")

    def num(key, default, lo, hi):
        raw = env.get(key)
        if raw is None:
            return default
        if not str(raw).strip().isdigit() or not lo <= int(raw) <= hi:
            errs.append(f"{key} must be an integer in {lo}..{hi}")
            return default
        return int(raw)
    access = num("TRADEFLOW_ACCESS_TTL_SECONDS", 3600, 60, 86400)
    days = num("TRADEFLOW_REFRESH_TTL_DAYS", 30, 1, 90)
    grace = num("TRADEFLOW_REFRESH_GRACE_SECONDS", 10, 0, 60)
    workers = num("WORKERS", 1, 1, 64)
    environment = env.get("TRADEFLOW_ENV", "development")
    if environment not in ("development", "test", "production"):
        errs.append("TRADEFLOW_ENV must be development|test|production")
    if workers != 1:
        warns.append("WORKERS != 1: the in-process login rate limiter is per worker (contract D10)")
    if environment == "production" and secret.startswith("dev"):
        errs.append("a development-looking secret is not allowed in production")
    if errs:
        raise ConfigError("; ".join(errs))
    return Settings(secret, access, days, grace, workers, environment), warns
