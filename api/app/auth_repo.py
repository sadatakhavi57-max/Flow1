"""SQL for authentication. Every function takes an open connection (dict rows). Nothing here decides policy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tradeflow_core.tokens import RefreshRow

_PRINCIPAL = """
SELECT u.id AS user_id, u.username, u.first_name, u.last_name, u.password_hash, u.is_active AS user_active,
       r.code AS role_code, r.name AS role_name, r.is_active AS role_active,
       o.id AS org_id, o.code AS org_code, o.name AS org_name, o.is_active AS org_active
  FROM users u
  JOIN roles r ON r.id = u.role_id
  JOIN organizations o ON o.id = u.organization_id
"""


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    first_name: str
    last_name: str
    password_hash: str
    role_code: str
    role_name: str
    org_id: str
    org_code: str
    org_name: str
    active: bool            # user AND role AND organization are all active

    def user_json(self) -> dict:
        return {"id": self.user_id, "username": self.username, "first_name": self.first_name, "last_name": self.last_name,
                "role": {"code": self.role_code, "name": self.role_name},
                "organization": {"id": self.org_id, "code": self.org_code, "name": self.org_name}}


def _principal(row) -> Principal | None:
    if row is None:
        return None
    return Principal(str(row["user_id"]), row["username"], row["first_name"], row["last_name"], row["password_hash"],
                     row["role_code"], row["role_name"], str(row["org_id"]), row["org_code"], row["org_name"],
                     bool(row["user_active"] and row["role_active"] and row["org_active"]))


def find_for_login(conn, org_code: str, username: str) -> Principal | None:
    return _principal(conn.execute(_PRINCIPAL + " WHERE o.code = %s AND u.username = %s", (org_code, username)).fetchone())


def load_principal(conn, user_id: str, org_id: str) -> Principal | None:
    return _principal(conn.execute(_PRINCIPAL + " WHERE u.id = %s AND u.organization_id = %s", (user_id, org_id)).fetchone())


def touch_login(conn, user_id: str, new_hash: str | None) -> None:
    if new_hash is None:
        conn.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
    else:
        conn.execute("UPDATE users SET last_login_at = NOW(), password_hash = %s WHERE id = %s", (new_hash, user_id))


def clean_ip(value) -> str | None:
    """audit_logs.ip_address is INET. Anything that is not a literal IP (e.g. Starlette's TestClient reports the host
    'testclient'; a proxy may send garbage) becomes NULL instead of failing the whole request with SQLSTATE 22P02."""
    import ipaddress
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def insert_audit(conn, e: dict) -> None:
    """`e` comes from tradeflow_core.audit.build_entry (closed vocabulary, secrets rejected)."""
    from psycopg.types.json import Jsonb
    conn.execute(
        "INSERT INTO audit_logs (organization_id, user_id, entity_type, entity_id, action, old_data, new_data, description, ip_address)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::inet)",
        (e["organization_id"], e["user_id"], e["entity_type"], e["entity_id"], e["action"],
         None if e["old_data"] is None else Jsonb(e["old_data"]), None if e["new_data"] is None else Jsonb(e["new_data"]),
         e["description"], clean_ip(e["ip_address"])))


class PgRefreshTx:
    """Implements tokens.Tx on one open transaction."""

    def __init__(self, conn):
        self.conn = conn

    def lock_by_hash(self, token_hash: str) -> RefreshRow | None:
        r = self.conn.execute(
            "SELECT rt.id, rt.user_id, u.organization_id, rt.token_hash, rt.expires_at, rt.revoked_at"
            "  FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id"
            " WHERE rt.token_hash = %s FOR UPDATE OF rt", (token_hash,)).fetchone()
        if r is None:
            return None
        return RefreshRow(str(r["id"]), str(r["user_id"]), str(r["organization_id"]), r["token_hash"], r["expires_at"], r["revoked_at"])

    def revoke(self, row_id: str, now: datetime) -> None:
        self.conn.execute("UPDATE refresh_tokens SET revoked_at = %s WHERE id = %s", (now, row_id))

    def revoke_all_active(self, user_id: str, now: datetime) -> int:
        return self.conn.execute("UPDATE refresh_tokens SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
                                 (now, user_id)).rowcount

    def insert(self, row: RefreshRow) -> None:
        self.conn.execute("INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) VALUES (%s, %s, %s, %s)",
                          (row.id, row.user_id, row.token_hash, row.expires_at))


class BoundStore:
    """tokens.RefreshService store that runs inside a transaction the CALLER owns (no commit here), so a token change and
    its audit row are one atomic unit (contract 13). Used for login and logout; refresh keeps its own transactions because
    the theft response must commit its revoke-all before the error is raised."""

    def __init__(self, conn):
        self.conn = conn

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield PgRefreshTx(self.conn)
        return cm()


class PgRefreshStore:
    def __init__(self, db):
        self.db = db

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            with self.db.tx() as conn:
                yield PgRefreshTx(conn)
        return cm()
