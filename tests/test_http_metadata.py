"""Discovery documents must match what MCP clients expect, exactly.

The single most common reason a remote connector is rejected is a protected
resource whose ``resource`` field differs from the URL the user typed, so
that value is compared as a raw string rather than through a URL type that
would normalise away the difference.
"""

from __future__ import annotations

from tests.conftest import PUBLIC_URL


async def test_authorization_server_metadata(client):
    """The AS document advertises everything a client needs to start."""
    response = await client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 200
    doc = response.json()

    assert doc["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in doc["grant_types_supported"]
    assert "refresh_token" in doc["grant_types_supported"]
    assert doc["registration_endpoint"].endswith("/register")
    assert doc["token_endpoint"].endswith("/token")
    assert doc["authorization_endpoint"].endswith("/authorize")
    assert doc["revocation_endpoint"].endswith("/revoke")


async def test_protected_resource_metadata_matches_public_url(client):
    """`resource` must equal the connector URL byte for byte."""
    response = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    doc = response.json()

    assert doc["resource"] == PUBLIC_URL
    assert isinstance(doc["resource"], str)
    assert doc["authorization_servers"], "at least one authorization server must be advertised"
    assert doc["scopes_supported"] == ["odoo:read", "odoo:write"]


async def test_bare_protected_resource_path_is_served(client):
    """Clients that probe the path-less well-known location get an answer."""
    response = await client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    assert response.json()["resource"] == PUBLIC_URL


async def test_both_protected_resource_documents_are_identical(client):
    """Two documents that disagree about the issuer break issuer validation.

    RFC 9207 has clients compare issuers by exact string, so a difference as
    small as a trailing slash between the two locations is a real defect.
    """
    suffixed = await client.get("/.well-known/oauth-protected-resource/mcp")
    bare = await client.get("/.well-known/oauth-protected-resource")
    assert suffixed.json() == bare.json()


async def test_the_advertised_issuer_matches_the_authorization_server(client):
    """The issuer in both documents must be the one the AS calls itself."""
    prm = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
    metadata = (await client.get("/.well-known/oauth-authorization-server")).json()
    assert prm["authorization_servers"][0] == metadata["issuer"]


async def test_health_endpoint_is_public(client):
    """Health checks must not require a token."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
