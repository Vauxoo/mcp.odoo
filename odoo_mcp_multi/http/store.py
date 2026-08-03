"""Persistent state for the embedded OAuth authorization server.

Everything the authorization server issues has to survive a restart —
registered clients, in-flight consent transactions, authorization codes,
tokens and the encrypted Odoo credentials behind them.

SQLite rather than a JSON file, for one decisive reason: redeeming an
authorization code must be atomic. A read-modify-write over a JSON document
lets two concurrent token requests redeem the same code, which is
authorization code replay. Here the redemption runs inside ``BEGIN
IMMEDIATE``, so the second request finds nothing.

Raw tokens are never stored — only their SHA-256 digests. Credentials and
client secrets are stored encrypted; client secrets must stay recoverable
because the SDK compares them with :func:`hmac.compare_digest`.
"""

from __future__ import annotations

import contextlib
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from odoo_mcp_multi.http.crypto import CredentialCipher, InvalidToken

SCHEMA_VERSION = 1

# How often a process bothers to delete expired rows.
PURGE_INTERVAL_SECONDS = 600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id   TEXT PRIMARY KEY,
  metadata_ct BLOB NOT NULL,
  client_name TEXT,
  created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS odoo_credentials (
  credential_id TEXT PRIMARY KEY,
  profile_ct    BLOB NOT NULL,
  odoo_url      TEXT NOT NULL,
  odoo_db       TEXT NOT NULL,
  odoo_login    TEXT NOT NULL,
  odoo_uid      INTEGER,
  protocol      TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  last_used_at  INTEGER
);

CREATE TABLE IF NOT EXISTS auth_txns (
  txn_id      TEXT PRIMARY KEY,
  client_id   TEXT NOT NULL,
  params_json TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  expires_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_codes (
  code                             TEXT PRIMARY KEY,
  client_id                        TEXT NOT NULL,
  scopes                           TEXT NOT NULL,
  code_challenge                   TEXT NOT NULL,
  redirect_uri                     TEXT NOT NULL,
  redirect_uri_provided_explicitly INTEGER NOT NULL,
  resource                         TEXT,
  credential_id                    TEXT NOT NULL
      REFERENCES odoo_credentials(credential_id) ON DELETE CASCADE,
  expires_at                       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS grants (
  grant_id      TEXT PRIMARY KEY,
  client_id     TEXT NOT NULL,
  credential_id TEXT NOT NULL
      REFERENCES odoo_credentials(credential_id) ON DELETE CASCADE,
  scopes        TEXT NOT NULL,
  resource      TEXT,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS access_tokens (
  token_hash TEXT PRIMARY KEY,
  grant_id   TEXT NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  token_hash TEXT PRIMARY KEY,
  grant_id   TEXT NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
  expires_at REAL
);

CREATE INDEX IF NOT EXISTS ix_at_exp    ON access_tokens(expires_at);
CREATE INDEX IF NOT EXISTS ix_rt_exp    ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS ix_codes_exp ON auth_codes(expires_at);
CREATE INDEX IF NOT EXISTS ix_txn_exp   ON auth_txns(expires_at);
CREATE INDEX IF NOT EXISTS ix_grants_cred ON grants(credential_id);
"""


def token_hash(token: str) -> str:
    """Return the digest under which a bearer token is stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    """Generate an opaque, high-entropy token."""
    return secrets.token_urlsafe(32)


class AuthStore:
    """SQLite-backed state for the authorization server."""

    def __init__(self, path: Path, cipher: CredentialCipher) -> None:
        self.path = Path(path)
        self.cipher = cipher
        self._last_purge = 0.0
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_schema()

    # -- connection --------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextlib.contextmanager
    def _transaction(self):
        """Yield a connection that is committed and then actually closed.

        sqlite3's own context manager commits but leaves the connection open,
        which leaks handles across the many short-lived calls made here.
        """
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._transaction() as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        try:
            self.path.chmod(0o600)
        except OSError:  # pragma: no cover - filesystems without POSIX modes
            pass

    # -- clients -----------------------------------------------------------

    def put_client(self, client_id: str, metadata: dict[str, Any], client_name: str = "") -> None:
        """Store (or replace) a registered OAuth client."""
        with self._transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO oauth_clients (client_id, metadata_ct, client_name, created_at) "
                "VALUES (?, ?, ?, ?)",
                (client_id, self.cipher.encrypt(metadata), client_name, int(time.time())),
            )

    def get_client(self, client_id: str) -> Optional[dict[str, Any]]:
        """Return a client's registration metadata, or None if unknown."""
        with self._transaction() as conn:
            row = conn.execute("SELECT metadata_ct FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
        if row is None:
            return None
        try:
            return self.cipher.decrypt(row["metadata_ct"])
        except (InvalidToken, ValueError):
            return None

    def list_clients(self) -> list[dict[str, Any]]:
        """Return every registered client for the ops CLI."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT client_id, client_name, created_at FROM oauth_clients ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Odoo credentials --------------------------------------------------

    def put_credential(self, profile_dict: dict[str, Any], uid: Optional[int]) -> str:
        """Encrypt and store one user's Odoo credentials; return its id."""
        credential_id = secrets.token_hex(16)
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO odoo_credentials (credential_id, profile_ct, odoo_url, odoo_db, odoo_login, "
                "odoo_uid, protocol, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    credential_id,
                    self.cipher.encrypt(profile_dict),
                    profile_dict.get("url", ""),
                    profile_dict.get("database", ""),
                    profile_dict.get("user", ""),
                    uid,
                    profile_dict.get("protocol", "auto"),
                    int(time.time()),
                ),
            )
        return credential_id

    def get_credential(self, credential_id: str) -> Optional[dict[str, Any]]:
        """Return the decrypted profile dict for a credential id."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT profile_ct FROM odoo_credentials WHERE credential_id = ?", (credential_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return self.cipher.decrypt(row["profile_ct"])
        except (InvalidToken, ValueError):
            return None

    def touch_credential(self, credential_id: str) -> None:
        """Record that a credential was used, at most once per minute."""
        now = int(time.time())
        with self._transaction() as conn:
            conn.execute(
                "UPDATE odoo_credentials SET last_used_at = ? "
                "WHERE credential_id = ? AND (last_used_at IS NULL OR last_used_at < ?)",
                (now, credential_id, now - 60),
            )

    # -- consent transactions ---------------------------------------------

    def put_txn(self, client_id: str, params_json: str, ttl: int) -> str:
        """Open a consent transaction and return its opaque id."""
        txn_id = new_token()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO auth_txns (txn_id, client_id, params_json, attempts, expires_at) VALUES (?, ?, ?, 0, ?)",
                (txn_id, client_id, params_json, time.time() + ttl),
            )
        return txn_id

    def get_txn(self, txn_id: str) -> Optional[dict[str, Any]]:
        """Return a live consent transaction, or None if unknown or expired."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM auth_txns WHERE txn_id = ? AND expires_at > ?", (txn_id, time.time())
            ).fetchone()
        return dict(row) if row else None

    def bump_txn_attempts(self, txn_id: str, limit: int) -> int:
        """Count a failed consent attempt; drop the transaction past ``limit``.

        Without this the consent form is an unauthenticated oracle for
        password-spraying the user's Odoo instance.
        """
        with self._transaction() as conn:
            conn.execute("UPDATE auth_txns SET attempts = attempts + 1 WHERE txn_id = ?", (txn_id,))
            row = conn.execute("SELECT attempts FROM auth_txns WHERE txn_id = ?", (txn_id,)).fetchone()
            attempts = int(row["attempts"]) if row else limit
            if attempts >= limit:
                conn.execute("DELETE FROM auth_txns WHERE txn_id = ?", (txn_id,))
        return attempts

    def delete_txn(self, txn_id: str) -> None:
        """Close a consent transaction."""
        with self._transaction() as conn:
            conn.execute("DELETE FROM auth_txns WHERE txn_id = ?", (txn_id,))

    # -- authorization codes ----------------------------------------------

    def put_code(
        self,
        *,
        client_id: str,
        scopes: list[str],
        code_challenge: str,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        resource: Optional[str],
        credential_id: str,
        ttl: int,
    ) -> str:
        """Mint a single-use authorization code bound to a credential."""
        code = new_token()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO auth_codes (code, client_id, scopes, code_challenge, redirect_uri, "
                "redirect_uri_provided_explicitly, resource, credential_id, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    code,
                    client_id,
                    " ".join(scopes),
                    code_challenge,
                    redirect_uri,
                    int(redirect_uri_provided_explicitly),
                    resource,
                    credential_id,
                    time.time() + ttl,
                ),
            )
        return code

    def peek_code(self, code: str, client_id: str) -> Optional[dict[str, Any]]:
        """Read an unexpired code without consuming it."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM auth_codes WHERE code = ? AND client_id = ? AND expires_at > ?",
                (code, client_id, time.time()),
            ).fetchone()
        return dict(row) if row else None

    def consume_code(self, code: str, client_id: str) -> Optional[dict[str, Any]]:
        """Atomically redeem a code; returns None if already used or expired.

        ``BEGIN IMMEDIATE`` takes the write lock before the read, so two
        concurrent redemptions of the same code cannot both succeed.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM auth_codes WHERE code = ? AND client_id = ? AND expires_at > ?",
                (code, client_id, time.time()),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return None
            conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
            conn.execute("COMMIT")
            return dict(row)
        except sqlite3.Error:  # pragma: no cover - defensive
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # -- grants and tokens -------------------------------------------------

    def create_grant(self, *, client_id: str, credential_id: str, scopes: list[str], resource: Optional[str]) -> str:
        """Open a grant: the unit that revocation deletes."""
        grant_id = secrets.token_hex(16)
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO grants (grant_id, client_id, credential_id, scopes, resource, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (grant_id, client_id, credential_id, " ".join(scopes), resource, int(time.time())),
            )
        return grant_id

    def get_grant(self, grant_id: str) -> Optional[dict[str, Any]]:
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone()
        return dict(row) if row else None

    def put_access_token(self, grant_id: str, ttl: int) -> tuple[str, float]:
        """Issue an access token; returns the raw token and its expiry."""
        token = new_token()
        expires_at = time.time() + ttl
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO access_tokens (token_hash, grant_id, expires_at) VALUES (?, ?, ?)",
                (token_hash(token), grant_id, expires_at),
            )
        return token, expires_at

    def get_access_token(self, token: str) -> Optional[dict[str, Any]]:
        """Return the grant behind a live access token, or None."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT a.token_hash, a.grant_id, a.expires_at, g.client_id, g.scopes, g.resource, "
                "g.credential_id FROM access_tokens a JOIN grants g ON g.grant_id = a.grant_id "
                "WHERE a.token_hash = ? AND a.expires_at > ?",
                (token_hash(token), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def put_refresh_token(self, grant_id: str, ttl: Optional[int]) -> str:
        """Issue a refresh token for a grant."""
        token = new_token()
        expires_at = time.time() + ttl if ttl else None
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO refresh_tokens (token_hash, grant_id, expires_at) VALUES (?, ?, ?)",
                (token_hash(token), grant_id, expires_at),
            )
        return token

    def get_refresh_token(self, token: str) -> Optional[dict[str, Any]]:
        """Return the grant behind a live refresh token, or None."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT r.token_hash, r.grant_id, r.expires_at, g.client_id, g.scopes, g.resource, "
                "g.credential_id FROM refresh_tokens r JOIN grants g ON g.grant_id = r.grant_id "
                "WHERE r.token_hash = ? AND (r.expires_at IS NULL OR r.expires_at > ?)",
                (token_hash(token), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def rotate_refresh_token(self, token: str) -> bool:
        """Atomically retire a refresh token and every access token it backs.

        Returns False when the token was already spent, which is what turns a
        replayed refresh into ``invalid_grant`` instead of a fresh token.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT grant_id FROM refresh_tokens WHERE token_hash = ? AND (expires_at IS NULL OR expires_at > ?)",
                (token_hash(token), time.time()),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return False
            conn.execute("DELETE FROM refresh_tokens WHERE token_hash = ?", (token_hash(token),))
            conn.execute("DELETE FROM access_tokens WHERE grant_id = ?", (row["grant_id"],))
            conn.execute("COMMIT")
            return True
        except sqlite3.Error:  # pragma: no cover - defensive
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def revoke_grant(self, grant_id: str) -> bool:
        """Delete a grant, its tokens, and the Odoo credentials behind it.

        Disconnecting the connector therefore also erases the stored Odoo
        password, which is the property worth advertising to users.
        """
        with self._transaction() as conn:
            row = conn.execute("SELECT credential_id FROM grants WHERE grant_id = ?", (grant_id,)).fetchone()
            if row is None:
                return False
            credential_id = row["credential_id"]
            conn.execute("DELETE FROM grants WHERE grant_id = ?", (grant_id,))
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM grants WHERE credential_id = ?", (credential_id,)
            ).fetchone()
            if remaining and remaining["n"] == 0:
                conn.execute("DELETE FROM odoo_credentials WHERE credential_id = ?", (credential_id,))
        return True

    def list_grants(self) -> list[dict[str, Any]]:
        """Return every live grant with its Odoo coordinates, for the ops CLI."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT g.grant_id, g.client_id, g.scopes, g.created_at, c.odoo_url, c.odoo_db, "
                "c.odoo_login, c.odoo_uid, c.last_used_at, "
                "(SELECT COUNT(*) FROM access_tokens a WHERE a.grant_id = g.grant_id) AS access_tokens "
                "FROM grants g JOIN odoo_credentials c ON c.credential_id = g.credential_id "
                "ORDER BY g.created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- housekeeping ------------------------------------------------------

    def purge_expired(self) -> dict[str, int]:
        """Delete expired transactions, codes and tokens; return the counts."""
        now = time.time()
        counts: dict[str, int] = {}
        with self._transaction() as conn:
            for table, column in (
                ("auth_txns", "expires_at"),
                ("auth_codes", "expires_at"),
                ("access_tokens", "expires_at"),
            ):
                cur = conn.execute(f"DELETE FROM {table} WHERE {column} <= ?", (now,))  # noqa: S608
                counts[table] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            cur = conn.execute("DELETE FROM refresh_tokens WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
            counts["refresh_tokens"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self._last_purge = time.monotonic()
        return counts

    def maybe_purge(self) -> None:
        """Purge at most once per interval, per process.

        Deliberately not a lifespan hook: in stateless HTTP mode the MCP
        lifespan runs on every request, and the session manager owns the app
        lifespan, so neither is a place to host a janitor.
        """
        now = time.monotonic()
        if now - self._last_purge < PURGE_INTERVAL_SECONDS:
            return
        self._last_purge = now
        try:
            self.purge_expired()
        except sqlite3.Error:  # pragma: no cover - housekeeping must never break a request
            pass
