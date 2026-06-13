"""Config profiles + credential resolution.

Mirrors the gh / AWS-CLI split: non-secret connection settings live in an INI
config file (``~/.config/chsql/config.ini``), while the password is kept out of
that file — preferably in the OS keyring (like ``gh``), or fetched at run time
from a ``password_command`` (like AWS ``credential_process``).

Resolution precedence for the password:
    CLI flag > $CLICKHOUSE_PASSWORD > OS keyring > password_command > (none)
"""

from __future__ import annotations

import configparser
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

KEYRING_SERVICE = "chsql"


def config_dir() -> Path:
    base = os.getenv("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "chsql"


def config_file() -> Path:
    return config_dir() / "config.ini"


# --------------------------------------------------------------------------- #
# config file (non-secret)
# --------------------------------------------------------------------------- #
def load_profile(name: str = "default") -> Dict[str, str]:
    """Return a profile's settings as a plain dict, or {} if none."""
    path = config_file()
    if not path.exists():
        return {}
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(path, encoding="utf-8")
    if cp.has_section(name):
        return dict(cp[name])
    return {}


def write_profile(name: str, settings: Dict[str, str]) -> Path:
    """Create/update a profile, preserving other profiles. Returns the path."""
    path = config_file()
    cp = configparser.ConfigParser(interpolation=None)
    if path.exists():
        cp.read(path, encoding="utf-8")
    cp[name] = {k: str(v) for k, v in settings.items() if v is not None and v != ""}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        cp.write(fh)
    return path


# --------------------------------------------------------------------------- #
# password backends
# --------------------------------------------------------------------------- #
def _account(user: str, host: str) -> str:
    return f"{user}@{host}"


def keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except Exception:
        return False


def get_keyring_password(user: str, host: str) -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, _account(user, host))
    except Exception:
        return None


def set_keyring_password(user: str, host: str, password: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, _account(user, host), password)


def run_password_command(command: str) -> Optional[str]:
    """Run a shell command and return its stdout (first line) as the password."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=15)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None
