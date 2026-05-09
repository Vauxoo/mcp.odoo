"""Profile configuration management for odoo-mcp-multi.

Handles loading, saving, and managing Odoo instance profiles
stored in ~/.config/odoo-mcp/profiles.json with secure permissions.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, model_validator


# Operations that can be gated by granular permissions.
# Metadata operations (list_available_profiles, get_version) are intentionally
# excluded — they are non-destructive and always allowed.
class Operation(str, Enum):
    SEARCH_READ = "search_read"
    WRITE = "write"
    UNLINK = "unlink"
    CREATE = "create"
    EXPORT_RECORDS = "export_records"
    IMPORT_RECORDS = "import_records"
    EXECUTE_KW = "execute_kw"
    LIST_MODELS = "list_models"
    LIST_FIELDS = "list_fields"


# Operations that are always allowed regardless of permission mode.
ALWAYS_ALLOWED_TOOLS = frozenset({"list_available_profiles", "get_version"})


class ProfilePermissions(BaseModel):
    """Permission configuration for a profile.

    Two modes:
    - 'full' (default): all operations allowed, backward compatible.
    - 'granular': only operations in allowed_operations are permitted.
    """

    mode: str = Field(default="full", description="Permission mode: 'full' or 'granular'")
    allowed_operations: list[str] = Field(
        default_factory=list,
        description="Operations allowed when mode is 'granular' (e.g., ['search_read', 'list_fields'])",
    )

    @model_validator(mode="after")
    def validate_operations(self) -> "ProfilePermissions":
        """Validate that all allowed_operations are valid Operation enum values."""
        valid_ops = {op.value for op in Operation}
        invalid = [op for op in self.allowed_operations if op not in valid_ops]
        if invalid:
            raise ValueError(f"Invalid operations: {invalid}. Valid operations: {sorted(valid_ops)}")
        return self


class OdooProfile(BaseModel):
    """Represents a single Odoo instance configuration.

    Supports two authentication modes:
    - **Legacy** (Odoo < 19): ``user`` + ``password`` via XML-RPC / JSON-RPC.
    - **JSON-2** (Odoo ≥ 19): ``api_key`` as Bearer token via /json/2.

    At least one of ``password`` or ``api_key`` must be provided.
    """

    name: str = Field(..., description="Profile identifier (e.g., 'prod', 'staging')")
    url: str = Field(..., description="Odoo instance URL (e.g., 'https://odoo.example.com')")
    database: str = Field(..., description="Database name")
    user: str = Field(default="", description="Username for authentication (legacy auth)")
    password: Optional[SecretStr] = Field(default=None, description="Password (legacy auth, stored securely)")
    api_key: Optional[SecretStr] = Field(default=None, description="API key for Odoo 19+ bearer auth")
    protocol: str = Field(default="auto", description="RPC protocol: auto, jsonrpcs, json2s, xmlrpcs")
    permissions: Optional[ProfilePermissions] = Field(
        default=None,
        description="Optional granular permissions. None = full access (backward compat).",
    )

    @model_validator(mode="after")
    def require_auth(self) -> "OdooProfile":
        """Ensure at least one authentication credential is provided."""
        if not self.password and not self.api_key:
            raise ValueError("Either 'password' (legacy auth) or 'api_key' (Odoo 19+ JSON-2) is required.")
        return self

    def is_operation_allowed(self, operation: str) -> bool:
        """Check if an operation is allowed under this profile's permissions.

        Always-allowed operations (metadata) bypass permission checks.
        Profiles without explicit permissions default to full access.
        """
        if operation in ALWAYS_ALLOWED_TOOLS:
            return True
        if self.permissions is None or self.permissions.mode == "full":
            return True
        return operation in self.permissions.allowed_operations

    def to_dict(self) -> dict:
        """Convert profile to dictionary for JSON serialization."""
        d: dict = {
            "name": self.name,
            "url": self.url,
            "database": self.database,
            "user": self.user,
            "protocol": self.protocol,
        }
        if self.password is not None:
            d["password"] = self.password.get_secret_value()
        if self.api_key is not None:
            d["api_key"] = self.api_key.get_secret_value()
        if self.permissions is not None:
            d["permissions"] = self.permissions.model_dump()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OdooProfile":
        """Create profile from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            database=data["database"],
            user=data.get("user", ""),
            password=SecretStr(data["password"]) if data.get("password") else None,
            api_key=SecretStr(data["api_key"]) if data.get("api_key") else None,
            protocol=data.get("protocol", "auto"),
            permissions=data.get("permissions"),
        )


class ProfileConfig(BaseModel):
    """Container for all profiles and configuration."""

    profiles: dict[str, OdooProfile] = Field(default_factory=dict)
    default_profile: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization."""
        return {
            "default_profile": self.default_profile,
            "profiles": {name: profile.to_dict() for name, profile in self.profiles.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProfileConfig:
        """Create config from dictionary."""
        profiles = {
            name: OdooProfile.from_dict(profile_data) for name, profile_data in data.get("profiles", {}).items()
        }
        return cls(profiles=profiles, default_profile=data.get("default_profile"))


def get_config_dir() -> Path:
    """Get the configuration directory path, creating it if necessary.

    Returns:
        Path to ~/.config/odoo-mcp/
    """
    config_dir = Path.home() / ".config" / "odoo-mcp"
    config_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get the configuration file path.

    Returns:
        Path to profiles.json
    """
    return get_config_dir() / "profiles.json"


def load_profiles() -> ProfileConfig:
    """Load profiles from the configuration file.

    Returns:
        ProfileConfig with all stored profiles
    """
    config_path = get_config_path()
    if not config_path.exists():
        return ProfileConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ProfileConfig.from_dict(data)


def save_profiles(config: ProfileConfig) -> None:
    """Save profiles to the configuration file with secure permissions.

    Args:
        config: ProfileConfig to persist
    """
    config_path = get_config_path()
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, mode=0o700, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)

    os.chmod(config_path, 0o600)


def get_profile(name: Optional[str] = None) -> Optional[OdooProfile]:
    """Get a specific profile by name or the default profile.

    Args:
        name: Profile name. If None, returns the default profile.

    Returns:
        OdooProfile if found, None otherwise
    """
    config = load_profiles()

    if name is None:
        name = config.default_profile

    if name is None:
        return None

    return config.profiles.get(name)


def add_profile(profile: OdooProfile, set_default: bool = False) -> None:
    """Add or update a profile in the configuration.

    Args:
        profile: OdooProfile to add
        set_default: If True, set this profile as the default
    """
    config = load_profiles()
    config.profiles[profile.name] = profile

    if set_default or config.default_profile is None:
        config.default_profile = profile.name

    save_profiles(config)


def remove_profile(name: str) -> bool:
    """Remove a profile from the configuration.

    Args:
        name: Profile name to remove

    Returns:
        True if profile was removed, False if not found
    """
    config = load_profiles()

    if name not in config.profiles:
        return False

    del config.profiles[name]

    if config.default_profile == name:
        config.default_profile = next(iter(config.profiles), None)

    save_profiles(config)
    return True


def rename_profile(old_name: str, new_name: str) -> tuple[bool, str]:
    """Rename a profile.

    Args:
        old_name: Current profile name
        new_name: Desired new name

    Returns:
        Tuple of (success, message)
    """
    config = load_profiles()

    if old_name not in config.profiles:
        return False, f"Profile '{old_name}' not found."

    if new_name in config.profiles:
        return False, f"Profile '{new_name}' already exists."

    config.profiles[new_name] = config.profiles.pop(old_name)

    if config.default_profile == old_name:
        config.default_profile = new_name

    save_profiles(config)
    return True, f"Profile '{old_name}' renamed to '{new_name}'."


def _get_auth_type(profile: OdooProfile) -> str:
    """Determine auth type from which credential is set on the profile."""
    if profile.api_key:
        return "api_key"
    if profile.password:
        return "password"
    return "none"


def list_profiles() -> list[dict]:
    """List all configured profiles.

    Returns:
        List of dicts with profile name, url, database, user, auth, and protocol
    """
    config = load_profiles()
    if not config.profiles:
        return []

    return [
        {
            "name": name,
            "url": profile.url,
            "database": profile.database,
            "user": profile.user,
            "protocol": profile.protocol,
            "auth": _get_auth_type(profile),
            "is_default": name == config.default_profile,
        }
        for name, profile in config.profiles.items()
    ]


def set_default_profile(name: str) -> bool:
    """Set the default profile.

    Args:
        name: Profile name to set as default

    Returns:
        True if successful, False if profile not found
    """
    config = load_profiles()

    if name not in config.profiles:
        return False

    config.default_profile = name
    save_profiles(config)
    return True


def resolve_profile(
    profile_name: Optional[str] = None,
    fallback: Optional[OdooProfile] = None,
) -> OdooProfile:
    """Resolve a profile name to an OdooProfile instance.

    Resolution order:
    1. Explicit profile_name lookup (raises if not found)
    2. Provided fallback (e.g. MCP server's startup profile)
    3. Default profile from the config file
    4. ValueError if nothing is configured

    Args:
        profile_name: Explicit profile name. If None, uses fallback/default.
        fallback: Optional fallback profile (avoids circular imports
            from server.py by letting the caller inject it).

    Returns:
        OdooProfile instance

    Raises:
        ValueError: If no profile can be resolved.
    """
    if profile_name:
        profile = get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found.")
        return profile

    if fallback:
        return fallback

    default = get_profile()
    if default:
        return default

    raise ValueError("No Odoo profile specified or configured as default.")
