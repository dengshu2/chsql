"""ClickHouse connection backends + the read-only safety guard.

Two transports, one uniform ``query() -> (rows, columns)`` interface:

* **native** (default) — ``clickhouse-driver``, the fast TCP protocol (9000/9440).
* **http**  — ``clickhouse-connect`` over the HTTP(S) interface (8123/8443/443),
  for servers exposed only through an HTTPS reverse proxy. Optional dependency:
  ``pip install 'chsql[http]'``.

Connection settings come from CLI flags, falling back to ``CLICKHOUSE_*`` env
vars (same names as mcp-clickhouse, so migration is zero-config).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from . import errors

# clickhouse-driver logs connection failures with a full traceback via the root
# logger; silence it so stderr carries only our structured JSON error.
for _name in ("clickhouse_driver", "clickhouse_connect"):
    _lg = logging.getLogger(_name)
    _lg.addHandler(logging.NullHandler())
    _lg.propagate = False

# Leading keyword -> category. Anything not listed is treated as a read.
_DDL = {"CREATE", "DROP", "TRUNCATE", "RENAME", "ATTACH", "DETACH", "REPLACE"}
_WRITE = {"INSERT", "ALTER", "DELETE", "UPDATE", "OPTIMIZE", "SYSTEM", "GRANT", "REVOKE"}

# ClickHouse error codes that mean "couldn't connect/authenticate", not "bad SQL".
_CONNECTION_CODES = {
    32,   # ATTEMPT_TO_READ_AFTER_EOF
    209,  # SOCKET_TIMEOUT
    210,  # NETWORK_ERROR
    516,  # AUTHENTICATION_FAILED
    519,  # NETWORK_ERROR variant
}

_HTTP_PORTS = {443, 8123, 8443}
_NATIVE_PORTS = {9000, 9440}
_COMMENT_RE = re.compile(r"(--[^\n]*\n)|(/\*.*?\*/)|(\s+)", re.DOTALL)


# --------------------------------------------------------------------------- #
# read-only guard
# --------------------------------------------------------------------------- #
def classify(sql: str) -> str:
    """Return 'read', 'write', or 'ddl' based on the leading SQL keyword."""
    stripped = sql.lstrip()
    while True:
        m = _COMMENT_RE.match(stripped)
        if not m:
            break
        stripped = stripped[m.end():]
    first = (stripped.split(None, 1) or [""])[0].upper().strip("(;")
    if first in _DDL:
        return "ddl"
    if first in _WRITE:
        return "write"
    return "read"


def _clean(exc: BaseException) -> str:
    """One-line message: drop the server-side C++ stack trace, collapse whitespace."""
    msg = str(exc)
    cut = msg.find("Stack trace:")
    if cut != -1:
        msg = msg[:cut]
    return " ".join(msg.split())


# --------------------------------------------------------------------------- #
# connection resolution
# --------------------------------------------------------------------------- #
def _resolve(conn: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Resolve protocol + concrete connection params from a partial dict."""
    secure = bool(conn.get("secure"))
    proto = (conn.get("protocol") or "auto").lower()
    port = conn.get("port")

    if proto == "auto":
        if port in _HTTP_PORTS:
            proto = "http"
        else:
            proto = "native"  # native is the default; http needs an explicit hint
    if proto not in ("native", "http"):
        errors.fail(errors.QUERY_ERROR, f"unknown protocol: {proto!r} (use native|http|auto)")

    if port is None:
        port = (8443 if secure else 8123) if proto == "http" else (9440 if secure else 9000)

    return proto, {
        "host": conn.get("host") or "localhost",
        "port": port,
        "user": conn.get("user") or "default",
        "password": conn.get("password") or "",
        "secure": secure,
        "database": conn.get("database") or "default",
    }


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #
class _NativeClient:
    def __init__(self, c: Dict[str, Any]):
        from clickhouse_driver import Client
        self._client = Client(
            host=c["host"], port=c["port"], user=c["user"], password=c["password"],
            secure=c["secure"], database=c["database"], connect_timeout=10,
        )

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None):
        from clickhouse_driver.errors import Error as CHError, NetworkError
        try:
            return self._client.execute(sql, params=params, with_column_types=True)
        except (OSError, EOFError) as exc:
            errors.fail(errors.CONNECTION_ERROR, f"connection failed: {_clean(exc)}")
        except CHError as exc:
            code = getattr(exc, "code", None)
            if isinstance(exc, NetworkError) or code in _CONNECTION_CODES:
                errors.fail(errors.CONNECTION_ERROR,
                            f"connection failed: {_clean(exc)}", clickhouse_code=code)
            errors.fail(errors.QUERY_ERROR,
                        f"query failed: {_clean(exc)}", clickhouse_code=code)


class _HttpClient:
    def __init__(self, c: Dict[str, Any]):
        import warnings
        try:
            with warnings.catch_warnings():
                # Hush urllib3's LibreSSL/OpenSSL warning so stderr stays clean.
                warnings.simplefilter("ignore")
                import clickhouse_connect
        except ImportError:
            errors.fail(errors.CONNECTION_ERROR,
                        "HTTP protocol requires clickhouse-connect — install with: "
                        "pip install 'chsql[http]'")
        from clickhouse_connect.driver.exceptions import OperationalError
        try:
            self._client = clickhouse_connect.get_client(
                host=c["host"], port=c["port"], username=c["user"], password=c["password"],
                secure=c["secure"], database=c["database"], connect_timeout=10, query_limit=0,
            )
        except OperationalError as exc:
            errors.fail(errors.CONNECTION_ERROR, f"connection failed: {_clean(exc)}")
        except Exception as exc:  # pragma: no cover - defensive
            errors.fail(errors.CONNECTION_ERROR, f"connection failed: {_clean(exc)}")

    def query(self, sql: str, params: Optional[Dict[str, Any]] = None):
        from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError
        try:
            result = self._client.query(sql, parameters=params or None)
            types = [getattr(t, "name", None) or str(t) for t in result.column_types]
            columns = list(zip(result.column_names, types))
            return result.result_rows, columns
        except OperationalError as exc:
            errors.fail(errors.CONNECTION_ERROR, f"connection failed: {_clean(exc)}")
        except DatabaseError as exc:
            errors.fail(errors.QUERY_ERROR, f"query failed: {_clean(exc)}")
        except Exception as exc:  # pragma: no cover - defensive
            errors.fail(errors.QUERY_ERROR, f"query failed: {_clean(exc)}")


def make_client(conn: Dict[str, Any]):
    """Build the right backend for the resolved protocol."""
    proto, resolved = _resolve(conn)
    return _HttpClient(resolved) if proto == "http" else _NativeClient(resolved)


def run(client, sql: str, params: Optional[Dict[str, Any]] = None
        ) -> Tuple[List[tuple], List[Tuple[str, str]]]:
    """Execute a query through a backend, returning (rows, columns)."""
    return client.query(sql, params=params)
