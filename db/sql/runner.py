"""TradeFlow PostgreSQL migration runner.

Contract
  * Migration files are named  NNN_name.sql  (NNN = at least 3 digits) and live in ONE folder.
    Default folder: the folder that contains this file (override: --migrations-dir or
    TRADEFLOW_MIGRATIONS_DIR).
  * Versions must be within 001..999 (anything else, e.g. 000 or 1000, is rejected - it must never be
    silently classified as a seed).
  * Versions 001..899 are schema migrations: applied in order, once, each in its own transaction.
    The runner itself records version/name/checksum in schema_migrations in that SAME transaction,
    so a migration can never be "applied but unchecksummed".
  * Versions 900..999 are development seed files. They are NEVER applied unless --include-dev-seed
    is given, they are not recorded, they must be idempotent, and they are refused when
    TRADEFLOW_ENV is production/prod.
  * Applied migrations are immutable (checksum), may not disappear, and new migrations may not be
    older than the newest applied one (no out-of-order application).
  * One runner at a time (PostgreSQL advisory lock).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{3,})_(?P<name>[a-z0-9_]+)\.sql$")
SEED_MIN_VERSION = 900
LOCK_KEY_SQL = "hashtextextended('tradeflow:migrations', 0)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("tradeflow.migrations")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str

    @property
    def is_seed(self) -> bool:
        return int(self.version) >= SEED_MIN_VERSION


def calculate_checksum(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def discover_files(migrations_dir: Path) -> tuple[list[Migration], list[Migration]]:
    """Return (schema_migrations, dev_seeds), each sorted by numeric version."""
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migration path not found: {migrations_dir}")
    if not migrations_dir.is_dir():
        raise NotADirectoryError(f"Migration path is not a directory: {migrations_dir}")

    found: list[Migration] = []
    seen: dict[int, str] = {}

    for path in migrations_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".sql":
            continue
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(
                f"Invalid migration filename: {path.name}. Expected format: NNN_name.sql (NNN >= 3 digits)"
            )
        number = int(match.group("version"))
        if not 1 <= number <= 999:
            raise ValueError(
                f"Invalid migration version {match.group('version')} in {path.name}: "
                "versions must be between 001 and 999 (900-999 are reserved for dev seed files)."
            )
        if number in seen:
            raise ValueError(f"Duplicate migration version {number}: {seen[number]} and {path.name}")
        seen[number] = path.name
        found.append(
            Migration(match.group("version"), match.group("name"), path, calculate_checksum(path))
        )

    found.sort(key=lambda m: int(m.version))
    migrations = [m for m in found if not m.is_seed]
    seeds = [m for m in found if m.is_seed]
    if not migrations:
        raise ValueError(f"No migration files found in: {migrations_dir}")
    return migrations, seeds


def schema_migrations_exists(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        return bool(cur.fetchone()[0])


def load_applied_migrations(conn: psycopg.Connection) -> dict[str, tuple[str, str | None]]:
    if not schema_migrations_exists(conn):
        return {}
    with conn.cursor() as cur:
        cur.execute("SELECT version, name, checksum FROM schema_migrations")
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def validate_applied_migrations(
    migrations: list[Migration], applied: dict[str, tuple[str, str | None]]
) -> None:
    migration_map = {m.version: m for m in migrations}
    for version, (name, stored_checksum) in applied.items():
        migration = migration_map.get(version)
        if migration is None:
            raise RuntimeError(f"Database contains migration {version}, but its SQL file is missing.")
        if migration.name != name:
            raise RuntimeError(
                f"Migration name mismatch for {version}: database='{name}', file='{migration.name}'."
            )
        if stored_checksum is not None and stored_checksum != migration.checksum:
            raise RuntimeError(
                f"Checksum mismatch for migration {version}. Do not edit an applied migration; create a new one."
            )


def find_pending(
    migrations: list[Migration], applied: dict[str, tuple[str, str | None]]
) -> list[Migration]:
    pending = [m for m in migrations if m.version not in applied]
    if applied and pending:
        newest_applied = max(int(v) for v in applied)
        late = [m.path.name for m in pending if int(m.version) < newest_applied]
        if late:
            raise RuntimeError(
                "Out-of-order migration(s) would be applied below the newest applied version "
                f"{newest_applied:03d}: {', '.join(late)}. Renumber them above it."
            )
    return pending


def acquire_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT pg_advisory_lock({LOCK_KEY_SQL})")


def release_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT pg_advisory_unlock({LOCK_KEY_SQL})")


def apply_migration(conn: psycopg.Connection, migration: Migration) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    if not sql.strip():
        raise RuntimeError(f"Migration file is empty: {migration.path.name}")

    logger.info("Applying %s", migration.path.name)
    # Real BEGIN/COMMIT (the connection is in autocommit mode): migration SQL, registration and
    # checksum are one atomic unit.
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(sql)
            # A migration may register itself (001 does); the runner is the authority on
            # name/checksum either way.
            cur.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s) "
                "ON CONFLICT (version) DO UPDATE SET name = EXCLUDED.name, checksum = EXCLUDED.checksum "
                "WHERE schema_migrations.checksum IS NULL "
                "RETURNING version",
                (migration.version, migration.name, migration.checksum),
            )
            if cur.fetchone() is None:
                raise RuntimeError(
                    f"Migration {migration.version} could not be registered in schema_migrations "
                    "(already registered with a checksum)."
                )
    logger.info("Applied %s", migration.path.name)


def apply_seed(conn: psycopg.Connection, seed: Migration) -> None:
    sql = seed.path.read_text(encoding="utf-8")
    logger.info("Applying DEV SEED %s (idempotent, not recorded)", seed.path.name)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(sql)


def run(database_url: str, migrations_dir: Path, include_dev_seed: bool = False) -> None:
    if include_dev_seed and os.getenv("TRADEFLOW_ENV", "").strip().lower() in {"prod", "production"}:
        raise RuntimeError("Refusing to apply development seed files: TRADEFLOW_ENV is production.")

    migrations, seeds = discover_files(migrations_dir)
    logger.info(
        "Found %d migration(s) and %d dev seed file(s) in %s", len(migrations), len(seeds), migrations_dir
    )

    with psycopg.connect(database_url, autocommit=True) as conn:
        acquire_migration_lock(conn)
        try:
            applied = load_applied_migrations(conn)
            validate_applied_migrations(migrations, applied)
            pending = find_pending(migrations, applied)

            if not pending:
                logger.info("Database is up to date.")
            else:
                for migration in pending:
                    apply_migration(conn, migration)
                logger.info("All pending migrations applied successfully.")

            if include_dev_seed:
                for seed in seeds:
                    apply_seed(conn, seed)
        finally:
            release_migration_lock(conn)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradeFlow PostgreSQL migration runner")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection string (default: $DATABASE_URL).",
    )
    parser.add_argument(
        "--migrations-dir",
        default=os.getenv("TRADEFLOW_MIGRATIONS_DIR"),
        help="Folder with NNN_name.sql files (default: the folder containing runner.py).",
    )
    parser.add_argument(
        "--include-dev-seed",
        action="store_true",
        help="Also apply 9xx development seed files. Never use in production.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        logger.error("--database-url or DATABASE_URL is required")
        return 1
    migrations_dir = (
        Path(args.migrations_dir).resolve() if args.migrations_dir else Path(__file__).resolve().parent
    )

    try:
        run(args.database_url, migrations_dir, include_dev_seed=args.include_dev_seed)
        return 0
    except (FileNotFoundError, NotADirectoryError, ValueError, RuntimeError, psycopg.Error) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
