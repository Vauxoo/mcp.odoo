"""Configuration for ``odoo-mcp serve``.

Everything the HTTP server needs is derived from a single ``--public-url``:
the exact string a user pastes into their MCP client. Getting that derivation
right is what makes a connector work — the ``resource`` field of the protected
resource metadata must match that URL byte for byte, or the client refuses the
connection.

The derivation is a pure function so it can be tested without a socket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Scopes this server understands. Both are granted together: the transport
# gate enforces `required_scopes`, and advertising a read-only scope the
# server does not actually enforce per-tool would be a lie to the client.
SCOPE_READ = "odoo:read"
SCOPE_WRITE = "odoo:write"
DEFAULT_SCOPES = [SCOPE_READ, SCOPE_WRITE]

DEFAULT_PORT = 5010
DEFAULT_PATH = "/mcp"
DEFAULT_ACCESS_TOKEN_TTL = 3600
DEFAULT_REFRESH_TOKEN_TTL = 30 * 24 * 3600
DEFAULT_AUTH_CODE_TTL = 300
DEFAULT_TXN_TTL = 600
DEFAULT_ODOO_TIMEOUT = 60
DEFAULT_MAX_CONCURRENCY = 32

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

# Where the hosted Claude surfaces send the user back after consent, and the
# origin those requests carry.
CLAUDE_ORIGIN = "https://claude.ai"
CLAUDE_REDIRECT_URI = f"{CLAUDE_ORIGIN}/api/mcp/auth_callback"


class ConfigError(ValueError):
    """Raised when the serve configuration cannot produce a working server."""


def is_loopback(host: str) -> bool:
    """Return True if ``host`` only accepts connections from this machine."""
    return host.strip("[]") in {h.strip("[]") for h in LOOPBACK_HOSTS}


@dataclass
class HttpServeConfig:
    """Resolved settings for one ``odoo-mcp serve`` process."""

    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    path: str = DEFAULT_PATH
    public_url: Optional[str] = None
    auth_enabled: bool = True
    json_response: bool = True
    stateless: bool = True
    state_db: Optional[Path] = None
    secret_key_file: Optional[Path] = None
    access_token_ttl: int = DEFAULT_ACCESS_TOKEN_TTL
    refresh_token_ttl: int = DEFAULT_REFRESH_TOKEN_TTL
    odoo_timeout: int = DEFAULT_ODOO_TIMEOUT
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    allowed_odoo_hosts: tuple[str, ...] = ()
    log_level: str = "INFO"

    # Derived in __post_init__
    issuer_url: str = field(init=False, default="")
    resource_url: str = field(init=False, default="")
    netloc: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            self.path = "/" + self.path

        if self.public_url:
            self._derive_from_public_url()
        else:
            if self.auth_enabled:
                raise ConfigError(
                    "--public-url is required with --auth oauth. Pass the exact URL your "
                    "users will paste into their MCP client, e.g. https://odoo-mcp.example.com/mcp"
                )
            self.netloc = f"{self.host}:{self.port}"
            self.issuer_url = f"http://{self.netloc}"
            self.resource_url = f"http://{self.netloc}{self.path}"

        if self.state_db is None:
            self.state_db = _default_config_dir() / "http-state.db"
        if self.secret_key_file is None:
            self.secret_key_file = _default_config_dir() / "http-secret.key"

    def _derive_from_public_url(self) -> None:
        parsed = urlparse(self.public_url or "")
        if parsed.scheme not in ("http", "https"):
            raise ConfigError(f"--public-url must be an http(s) URL, got '{self.public_url}'.")
        if not parsed.netloc:
            raise ConfigError(f"--public-url is missing a host: '{self.public_url}'.")
        if parsed.fragment or parsed.query:
            raise ConfigError("--public-url must not contain a query string or fragment.")

        hostname = parsed.hostname or ""
        if parsed.scheme == "http" and not is_loopback(hostname):
            raise ConfigError(
                f"--public-url must use https for a public host ('{hostname}'). MCP clients refuse to send "
                "bearer tokens over plaintext."
            )

        public_path = parsed.path.rstrip("/")
        if public_path and public_path != self.path:
            raise ConfigError(
                f"--path is '{self.path}' but --public-url ends in '{public_path}'. They must match, or the "
                "protected resource metadata will advertise a resource your users cannot reach. "
                f"Pass --path {public_path}."
            )
        if not public_path and self.path != DEFAULT_PATH:
            raise ConfigError(
                f"--public-url has no path but --path is '{self.path}'. Append it to --public-url: "
                f"{self.public_url.rstrip('/')}{self.path}"
            )

        self.netloc = parsed.netloc
        self.issuer_url = f"{parsed.scheme}://{parsed.netloc}"
        self.resource_url = f"{self.issuer_url}{public_path or self.path}"

    # -- URLs the OAuth layer needs ---------------------------------------

    @property
    def login_url(self) -> str:
        """Absolute URL of the Odoo consent form."""
        return f"{self.issuer_url}/odoo/login"

    @property
    def protected_resource_path(self) -> str:
        """Path of the RFC 9728 document the SDK mounts for this resource."""
        return f"/.well-known/oauth-protected-resource{self.path}"

    def validate_runtime(self) -> None:
        """Reject combinations that would expose an unauthenticated server."""
        if not self.auth_enabled:
            if not is_loopback(self.host):
                raise ConfigError(
                    f"Refusing to bind {self.host} without authentication. --auth local only binds "
                    "127.0.0.1, localhost or ::1; use --auth oauth to serve other machines."
                )
            if self.public_url and urlparse(self.public_url).scheme == "https":
                raise ConfigError(
                    "--auth local cannot be combined with an https --public-url: the URL promises a "
                    "publicly reachable server that anyone could then use without credentials."
                )


def _default_config_dir() -> Path:
    """Return the shared odoo-mcp config directory, creating it if needed."""
    from odoo_mcp_multi.config import get_config_dir

    return get_config_dir()
