"""Config loading + persistence for the wp CLI.

Layered lookup (highest priority first):
  1. CLI flags (--base-url, --internal-key)
  2. Env vars WP_BASE_URL, WP_INTERNAL_KEY
  3. ~/.config/workplanner/config.toml (default profile)

The config file supports multiple profiles; the active one is selected
either by `--profile NAME` or the file's `default_profile` field.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "workplanner"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Profile:
    base_url: str
    internal_key: str
    name: str = "default"


def _read_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def load(profile_name: str | None, base_url_flag: str | None, key_flag: str | None) -> Profile:
    """Resolve the active profile given the layered lookup rules.

    Raises FileNotFoundError if no config exists and the user didn't supply
    enough via flags/env to construct one inline.
    """
    file_data = _read_file()
    profiles = file_data.get("profile", {})
    chosen_name = profile_name or file_data.get("default_profile") or "default"

    base_url = base_url_flag or os.environ.get("WP_BASE_URL")
    internal_key = key_flag or os.environ.get("WP_INTERNAL_KEY")

    profile_entry = profiles.get(chosen_name, {}) if isinstance(profiles, dict) else {}
    base_url = base_url or profile_entry.get("base_url")
    internal_key = internal_key or profile_entry.get("internal_key")

    if not base_url or not internal_key:
        hint = (
            "Missing base_url or internal_key.\n"
            "Run `wp config init` to create ~/.config/workplanner/config.toml,\n"
            "or set WP_BASE_URL and WP_INTERNAL_KEY in the environment."
        )
        raise FileNotFoundError(hint)

    return Profile(base_url=base_url, internal_key=internal_key, name=chosen_name)


def save_profile(name: str, base_url: str, internal_key: str, make_default: bool) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = _read_file()
    profiles = data.get("profile")
    if not isinstance(profiles, dict):
        profiles = {}
    profiles[name] = {"base_url": base_url, "internal_key": internal_key}
    data["profile"] = profiles
    if make_default or "default_profile" not in data:
        data["default_profile"] = name
    with CONFIG_FILE.open("wb") as f:
        tomli_w.dump(data, f)
    # The file holds a secret — keep it 0600.
    os.chmod(CONFIG_FILE, 0o600)
    return CONFIG_FILE


def list_profiles() -> tuple[str | None, dict]:
    """Return (default_profile, {name: {base_url, ...}})."""
    data = _read_file()
    profiles = data.get("profile", {})
    if not isinstance(profiles, dict):
        profiles = {}
    return data.get("default_profile"), profiles
