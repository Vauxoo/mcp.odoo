"""Per-request Odoo credentials for HTTP mode.

In stdio mode a single process serves a single user, so ``operations``
keeps the active profile in a module global set once at startup.

Over HTTP the same process serves many users, each authenticated with their
own Odoo credentials, so the active profile must be scoped to the request.
This module holds that scope in a :class:`~contextvars.ContextVar`.

Resolution order used by :func:`get_request_profile`:

1. A profile explicitly pushed with :func:`set_request_profile` (tests, and
   any caller that wants to bind credentials by hand).
2. The profile carried by the authenticated OAuth token, which the HTTP
   authorization provider attaches to the ``AccessToken`` it returns.

Both are ``None`` in stdio mode, which keeps the legacy fallback path intact.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from odoo_mcp_multi.config import OdooProfile

_request_profile: ContextVar[Optional[Any]] = ContextVar("odoo_mcp_request_profile", default=None)


def set_request_profile(profile: Optional["OdooProfile"]) -> Token:
    """Bind an Odoo profile to the current context.

    Returns the token needed to restore the previous value; pass it to
    :func:`reset_request_profile` when the scope ends.
    """
    return _request_profile.set(profile)


def reset_request_profile(token: Token) -> None:
    """Restore the profile that was bound before ``token`` was issued."""
    _request_profile.reset(token)


def get_request_profile() -> Optional["OdooProfile"]:
    """Return the Odoo profile bound to the current request, if any.

    Falls back to the profile carried by the authenticated OAuth access
    token. Returns ``None`` in stdio mode, where no request scope exists.
    """
    profile = _request_profile.get()
    if profile is not None:
        return profile

    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
    except ImportError:  # pragma: no cover - mcp always ships this module
        return None

    try:
        token = get_access_token()
    except LookupError:  # pragma: no cover - defensive, contextvar has a default
        return None

    return getattr(token, "odoo_profile", None) if token is not None else None
