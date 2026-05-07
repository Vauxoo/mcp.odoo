"""Tests for config.py profile management.

Uses pytest's tmp_path fixture to redirect the config directory,
ensuring tests are hermetic — no real ~/.config/odoo-mcp/ is touched.
"""

import pytest
from pydantic import SecretStr

from odoo_mcp_multi.config import (
    OdooProfile,
    ProfileConfig,
    add_profile,
    get_profile,
    list_profiles,
    load_profiles,
    remove_profile,
    save_profiles,
    set_default_profile,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temporary directory for every test."""
    monkeypatch.setattr("odoo_mcp_multi.config.get_config_dir", lambda: tmp_path)
    return tmp_path


def _make_profile(name: str = "test", url: str = "https://odoo.example.com") -> OdooProfile:
    return OdooProfile(
        name=name,
        url=url,
        database="db",
        user="admin",
        password=SecretStr("secret"),
    )


# ---------------------------------------------------------------------------
# load_profiles
# ---------------------------------------------------------------------------


def test_load_profiles_returns_empty_if_no_file():
    config = load_profiles()
    assert config.profiles == {}
    assert config.default_profile is None


def test_load_profiles_after_save(tmp_path):
    profile = _make_profile()
    config = ProfileConfig(profiles={"test": profile}, default_profile="test")
    save_profiles(config)

    loaded = load_profiles()
    assert "test" in loaded.profiles
    assert loaded.default_profile == "test"


# ---------------------------------------------------------------------------
# save_profiles (file creation and content)
# ---------------------------------------------------------------------------


def test_save_profiles_creates_file(tmp_path):
    profile = _make_profile()
    config = ProfileConfig(profiles={"test": profile}, default_profile="test")
    save_profiles(config)

    config_file = tmp_path / "profiles.json"
    assert config_file.exists()


def test_save_profiles_password_roundtrip(tmp_path):
    """Password must survive save→load without corruption."""
    profile = _make_profile()
    config = ProfileConfig(profiles={"test": profile}, default_profile="test")
    save_profiles(config)

    loaded = load_profiles()
    assert loaded.profiles["test"].password.get_secret_value() == "secret"


# ---------------------------------------------------------------------------
# add_profile
# ---------------------------------------------------------------------------


def test_add_profile_single(tmp_path):
    add_profile(_make_profile("prod"))
    config = load_profiles()
    assert "prod" in config.profiles


def test_add_profile_sets_default_when_first(tmp_path):
    """First profile added must become the default automatically."""
    add_profile(_make_profile("prod"))
    config = load_profiles()
    assert config.default_profile == "prod"


def test_add_profile_does_not_override_existing_default(tmp_path):
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"))
    config = load_profiles()
    assert config.default_profile == "prod"  # first one remains default


def test_add_profile_force_set_default(tmp_path):
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"), set_default=True)
    config = load_profiles()
    assert config.default_profile == "staging"


def test_add_profile_updates_existing(tmp_path):
    """Adding a profile with an existing name updates it in-place."""
    add_profile(_make_profile("prod", url="https://old.example.com"))
    add_profile(_make_profile("prod", url="https://new.example.com"))
    config = load_profiles()
    assert config.profiles["prod"].url == "https://new.example.com"
    assert len(config.profiles) == 1  # not duplicated


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


def test_get_profile_by_name(tmp_path):
    add_profile(_make_profile("prod"))
    profile = get_profile("prod")
    assert profile is not None
    assert profile.name == "prod"


def test_get_profile_returns_default_when_name_is_none(tmp_path):
    add_profile(_make_profile("prod"))
    profile = get_profile(None)
    assert profile is not None
    assert profile.name == "prod"


def test_get_profile_returns_none_for_unknown_name(tmp_path):
    add_profile(_make_profile("prod"))
    profile = get_profile("nonexistent")
    assert profile is None


def test_get_profile_returns_none_when_no_profiles(tmp_path):
    assert get_profile(None) is None


# ---------------------------------------------------------------------------
# remove_profile
# ---------------------------------------------------------------------------


def test_remove_profile_existing(tmp_path):
    add_profile(_make_profile("prod"))
    result = remove_profile("prod")
    assert result is True
    assert get_profile("prod") is None


def test_remove_profile_nonexistent_returns_false(tmp_path):
    result = remove_profile("nonexistent")
    assert result is False


def test_remove_default_profile_updates_default(tmp_path):
    """When the default profile is removed, the next available one becomes default."""
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"))
    assert load_profiles().default_profile == "prod"

    remove_profile("prod")
    config = load_profiles()
    assert "prod" not in config.profiles
    # Default must be updated to the remaining profile
    assert config.default_profile == "staging"


def test_remove_last_profile_leaves_no_default(tmp_path):
    add_profile(_make_profile("prod"))
    remove_profile("prod")
    config = load_profiles()
    assert config.default_profile is None


# ---------------------------------------------------------------------------
# set_default_profile
# ---------------------------------------------------------------------------


def test_set_default_profile_success(tmp_path):
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"))
    result = set_default_profile("staging")
    assert result is True
    assert load_profiles().default_profile == "staging"


def test_set_default_profile_nonexistent_returns_false(tmp_path):
    result = set_default_profile("nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------


def test_list_profiles_empty(tmp_path):
    assert list_profiles() == []


def test_list_profiles_shows_all(tmp_path):
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"))
    profiles = list_profiles()
    names = {p["name"] for p in profiles}
    assert names == {"prod", "staging"}


def test_list_profiles_marks_default(tmp_path):
    add_profile(_make_profile("prod"))
    add_profile(_make_profile("staging"), set_default=True)
    profiles = list_profiles()
    defaults = [p for p in profiles if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "staging"


def test_list_profiles_no_password_exposed(tmp_path):
    """Password must NEVER appear in list_profiles output."""
    add_profile(_make_profile("prod"))
    profiles = list_profiles()
    for p in profiles:
        assert "password" not in p


def test_list_profiles_auth_field_password(tmp_path):
    """Auth field should be 'password' when profile uses password auth."""
    add_profile(_make_profile("prod"))
    profiles = list_profiles()
    assert profiles[0]["auth"] == "password"


def test_list_profiles_auth_field_api_key(tmp_path):
    """Auth field should be 'api_key' when profile uses api_key auth."""
    profile = OdooProfile(
        name="prod19",
        url="https://odoo19.example.com",
        database="mydb",
        api_key=SecretStr("myapikey123"),
        user="admin@example.com",
    )
    add_profile(profile)
    profiles = list_profiles()
    api_key_profiles = [p for p in profiles if p["name"] == "prod19"]
    assert api_key_profiles[0]["auth"] == "api_key"
    # user is informational only — auth must NOT be inferred from user presence
    assert api_key_profiles[0]["user"] == "admin@example.com"


# ---------------------------------------------------------------------------
# T14–T16: OdooProfile api_key support (Odoo 19+ JSON-2)
# ---------------------------------------------------------------------------


def test_profile_with_api_key_only():
    """T14: OdooProfile accepts api_key without password for Odoo 19+."""
    p = OdooProfile(
        name="prod19",
        url="https://odoo19.example.com",
        database="mydb",
        api_key=SecretStr("myapikey123"),
    )
    assert p.api_key is not None
    assert p.api_key.get_secret_value() == "myapikey123"
    assert p.password is None


def test_profile_requires_at_least_one_auth():
    """T15: OdooProfile raises ValidationError if neither password nor api_key given."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OdooProfile(
            name="bad",
            url="https://example.com",
            database="mydb",
        )


def test_profile_to_dict_with_api_key():
    """T16: to_dict() includes api_key and omits password when only api_key set."""
    p = OdooProfile(
        name="prod19",
        url="https://odoo19.example.com",
        database="mydb",
        api_key=SecretStr("myapikey123"),
    )
    d = p.to_dict()
    assert d["api_key"] == "myapikey123"
    assert "password" not in d


def test_profile_from_dict_with_api_key():
    """T16b: from_dict() loads a profile that only has api_key."""
    data = {
        "name": "prod19",
        "url": "https://odoo19.example.com",
        "database": "mydb",
        "api_key": "myapikey123",
        "protocol": "json2s",
    }
    p = OdooProfile.from_dict(data)
    assert p.api_key is not None
    assert p.api_key.get_secret_value() == "myapikey123"
    assert p.password is None
    assert p.protocol == "json2s"


def test_profile_api_key_roundtrip(tmp_path):
    """T16c: api_key survives save → load without corruption."""
    profile = OdooProfile(
        name="prod19",
        url="https://odoo19.example.com",
        database="mydb",
        api_key=SecretStr("secretapikey"),
        protocol="json2s",
    )
    from odoo_mcp_multi.config import ProfileConfig, load_profiles, save_profiles

    config = ProfileConfig(profiles={"prod19": profile}, default_profile="prod19")
    save_profiles(config)
    loaded = load_profiles()
    assert loaded.profiles["prod19"].api_key.get_secret_value() == "secretapikey"
