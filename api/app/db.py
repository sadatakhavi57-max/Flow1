"""One short transaction per unit of work (no pool in Slice 01: simple and correct; a pool is a later optimisation).
Connections use dict rows. Commit on normal exit, rollback on any exception."""
from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from tradeflow_core.errors import AppError, map_pg_error


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def tx(self):
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


    def run(self, fn):
        """Run fn(conn) in one transaction. A deadlock or serialization failure is retried ONCE (contract 14.7);
        a second failure propagates and is rendered as 503 TEMPORARILY_UNAVAILABLE."""
        for attempt in (1, 2):
            try:
                with self.tx() as conn:
                    return fn(conn)
            except (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure):
                if attempt == 2:
                    raise


def to_app_error(e: psycopg.Error) -> AppError:
    """psycopg error -> contract error. SQL text and server messages never reach the client."""
    d = e.diag
    sqlstate = getattr(e, "sqlstate", None) or getattr(d, "sqlstate", None) or ""
    if isinstance(e, psycopg.OperationalError) and not sqlstate:
        sqlstate = "08000"                       # could not connect / connection lost -> TEMPORARILY_UNAVAILABLE
    return map_pg_error(sqlstate, getattr(d, "constraint_name", None), getattr(d, "message_primary", "") or "")
