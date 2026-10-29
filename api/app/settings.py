"""Process settings: core.config validates the security-relevant ones; the DSN is read here."""
from __future__ import annotations

import os
from dataclasses import dataclass

from tradeflow_core import config as core_config


@dataclass(frozen=True)
class AppSettings:
    core: core_config.Settings
    database_dsn: str
    warnings: tuple


def from_env(env=None) -> AppSettings:
    env = dict(os.environ if env is None else env)
    core, warns = core_config.load(env)
    dsn = env.get("TRADEFLOW_DATABASE_URL", "").strip()
    if not dsn:
        raise core_config.ConfigError("TRADEFLOW_DATABASE_URL is required (a libpq DSN, e.g. 'dbname=tradeflow')")
    return AppSettings(core, dsn, tuple(warns))
