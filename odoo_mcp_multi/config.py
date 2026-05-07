"""Profile configuration management for odoo-mcp-multi.

Handles loading, saving, and managing Odoo instance profiles
stored in ~/.config/odoo-mcp/profiles.json with secure permissions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, model_validator


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

    @model_validator(mode="after")
    def require_auth(self) -> "OdooProfile":
        """Ensure at least one authentication credential is provided."""
        if not self.password and not self.api_key:
            raise ValueError("Either 'password' (legacy auth) or 'api_key' (Odoo 19+ JSON-2) is required.")
        return self

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
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700)
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

    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700)

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


def list_profiles() -> list[dict]:
    """List all configured profiles.

    Returns:
        List of dicts with profile name, url, database, user, auth, and protocol
    """
    config = load_profiles()
    result = []

    for name, profile in config.profiles.items():
        # Auth type is determined by which credential is set,
        # not by the presence of a user string (informational in Odoo 19+).
        if profile.api_key:
            auth = "api_key"
        elif profile.password:
            auth = "password"
        else:
            auth = "none"

        result.append(
            {
                "name": name,
                "url": profile.url,
                "database": profile.database,
                "user": profile.user,
                "protocol": profile.protocol,
                "auth": auth,
                "is_default": name == config.default_profile,
            }
        )

    return result


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
