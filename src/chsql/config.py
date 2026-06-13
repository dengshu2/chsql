"""The one place a connection is stored: a single URL in the OS keyring.

No config files, no profiles, no separate password backends. A connection is a
URL (``clickhouse://user:pass@host:port/db?secure=1``); ``chsql login`` stores it
in the keyring, and that's the whole persistent-config surface.
"""

from __future__ import annotations

from typing import Optional

KEYRING_SERVICE = "chsql"
KEYRING_ACCOUNT = "url"


def keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except Exception:
        return False


def get_url() -> Optional[str]:
    """Return the stored connection URL, or None."""
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except Exception:
        return None


def set_url(url: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, url)


def delete_url() -> bool:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        return True
    except Exception:
        return False
