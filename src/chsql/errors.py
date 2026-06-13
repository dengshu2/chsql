"""Exit codes and structured error output for the Agent contract.

Data goes to stdout; every error goes to stderr as a single JSON object
``{"error": <message>, "code": <exit code>}`` so an agent can branch on the
exit code without parsing free text.
"""

from __future__ import annotations

import json
import sys

# Semantic exit codes — keep these stable; agents depend on them.
SUCCESS = 0
QUERY_ERROR = 1       # SQL is invalid / server rejected the query
CONNECTION_ERROR = 2  # could not reach / authenticate with the server
PERMISSION_ERROR = 3  # a write/DDL was blocked by the read-only guard


def fail(code: int, message: str, **extra) -> "SystemExit":
    """Print a structured error to stderr and raise to exit with ``code``."""
    payload = {"error": message, "code": code}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)
