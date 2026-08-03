"""The authorization store's security-critical guarantees.

Single-use codes, refresh rotation, revocation that reaches the stored
credentials, and encryption at rest. These are asserted directly against the
store rather than through HTTP, because each one is a property the protocol
layer trusts without re-checking.
"""

from __future__ import annotations

import time

import pytest

from odoo_mcp_multi.http.crypto import CredentialCipher, load_or_create_key
from odoo_mcp_multi.http.store import AuthStore

PROFILE = {
    "name": "oauth:db",
    "url": "https://odoo.example.com",
    "database": "db",
    "user": "someone@example.com",
    "password": "s3cret",
    "protocol": "jsonrpcs",
    "verify": True,
}


@pytest.fixture
def store(tmp_path):
    return AuthStore(tmp_path / "state.db", CredentialCipher.from_file(tmp_path / "key"))


def _code(store, credential_id, ttl=300):
    return store.put_code(
        client_id="c1",
        scopes=["odoo:read"],
        code_challenge="challenge",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        resource="https://odoo-mcp.me1980.com/mcp",
        credential_id=credential_id,
        ttl=ttl,
    )


# -- authorization codes ----------------------------------------------------


def test_a_code_can_only_be_redeemed_once(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    code = _code(store, credential_id)

    assert store.consume_code(code, "c1") is not None
    assert store.consume_code(code, "c1") is None, "replay must find nothing"


def test_a_code_belongs_to_one_client(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    code = _code(store, credential_id)
    assert store.consume_code(code, "someone-else") is None


def test_an_expired_code_is_not_redeemable(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    code = _code(store, credential_id, ttl=-1)
    assert store.peek_code(code, "c1") is None
    assert store.consume_code(code, "c1") is None


# -- tokens -----------------------------------------------------------------


def test_rotation_retires_the_previous_chain(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    grant_id = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    access, _ = store.put_access_token(grant_id, ttl=3600)
    refresh = store.put_refresh_token(grant_id, ttl=3600)

    assert store.rotate_refresh_token(refresh) is True
    assert store.get_refresh_token(refresh) is None
    assert store.get_access_token(access) is None, "rotation must invalidate the old access token"
    assert store.rotate_refresh_token(refresh) is False, "replay must fail"


def test_expired_access_token_does_not_resolve(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    grant_id = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    token, _ = store.put_access_token(grant_id, ttl=1)
    time.sleep(1.1)
    assert store.get_access_token(token) is None


def test_raw_tokens_are_never_stored(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    grant_id = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    token, _ = store.put_access_token(grant_id, ttl=3600)

    with store._connect() as conn:
        stored = [row[0] for row in conn.execute("SELECT token_hash FROM access_tokens")]
    assert token not in stored
    assert len(stored) == 1 and len(stored[0]) == 64


# -- revocation -------------------------------------------------------------


def test_revocation_erases_the_odoo_credentials(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    grant_id = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    token, _ = store.put_access_token(grant_id, ttl=3600)

    assert store.revoke_grant(grant_id) is True
    assert store.get_access_token(token) is None
    assert store.get_credential(credential_id) is None, "the stored Odoo password must be gone"
    assert store.revoke_grant(grant_id) is False


def test_credentials_survive_a_second_grant(store):
    """Revoking one connector must not break another sharing the credentials."""
    credential_id = store.put_credential(PROFILE, uid=2)
    first = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    second = store.create_grant(client_id="c2", credential_id=credential_id, scopes=["odoo:read"], resource=None)

    store.revoke_grant(first)
    assert store.get_credential(credential_id) is not None
    assert store.get_grant(second) is not None


# -- consent transactions ---------------------------------------------------


def test_attempts_are_capped(store):
    txn_id = store.put_txn("c1", "{}", ttl=600)
    for expected in range(1, 5):
        assert store.bump_txn_attempts(txn_id, limit=5) == expected
        assert store.get_txn(txn_id) is not None

    assert store.bump_txn_attempts(txn_id, limit=5) == 5
    assert store.get_txn(txn_id) is None, "the transaction must be cancelled at the limit"


def test_expired_transaction_is_invisible(store):
    txn_id = store.put_txn("c1", "{}", ttl=-1)
    assert store.get_txn(txn_id) is None


# -- encryption and housekeeping -------------------------------------------


def test_credentials_round_trip_through_encryption(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    assert store.get_credential(credential_id) == PROFILE

    with store._connect() as conn:
        ciphertext = conn.execute(
            "SELECT profile_ct FROM odoo_credentials WHERE credential_id = ?", (credential_id,)
        ).fetchone()[0]
    assert b"s3cret" not in ciphertext, "the secret must not be readable in the database"


def test_a_foreign_key_cannot_read_the_credentials(tmp_path):
    """A stolen database is useless without the separate key file."""
    store = AuthStore(tmp_path / "state.db", CredentialCipher.from_file(tmp_path / "key"))
    credential_id = store.put_credential(PROFILE, uid=2)

    other = AuthStore(tmp_path / "state.db", CredentialCipher.from_file(tmp_path / "other-key"))
    assert other.get_credential(credential_id) is None


def test_key_and_database_files_are_owner_only(tmp_path):
    store = AuthStore(tmp_path / "state.db", CredentialCipher.from_file(tmp_path / "key"))
    assert (tmp_path / "key").stat().st_mode & 0o077 == 0
    assert store.path.stat().st_mode & 0o077 == 0


def test_key_file_is_stable_across_loads(tmp_path):
    first = load_or_create_key(tmp_path / "key")
    assert load_or_create_key(tmp_path / "key") == first


def test_purge_only_removes_expired_rows(store):
    credential_id = store.put_credential(PROFILE, uid=2)
    grant_id = store.create_grant(client_id="c1", credential_id=credential_id, scopes=["odoo:read"], resource=None)
    live_token, _ = store.put_access_token(grant_id, ttl=3600)
    dead_token, _ = store.put_access_token(grant_id, ttl=-1)
    _code(store, credential_id, ttl=-1)
    store.put_txn("c1", "{}", ttl=-1)

    counts = store.purge_expired()
    assert counts["access_tokens"] == 1
    assert counts["auth_codes"] == 1
    assert counts["auth_txns"] == 1
    assert store.get_access_token(live_token) is not None
    assert store.get_access_token(dead_token) is None


def test_concurrent_connections_do_not_collide(store):
    """Two writers must serialize rather than raise 'database is locked'."""
    credential_id = store.put_credential(PROFILE, uid=2)
    codes = [_code(store, credential_id) for _ in range(10)]
    assert len({store.consume_code(code, "c1")["code"] for code in codes}) == 10
