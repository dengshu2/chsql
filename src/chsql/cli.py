"""chsql — Agent-friendly ClickHouse query CLI.

Subcommands: query, databases, tables, describe, login, logout, skill install.

A connection is a single URL (``clickhouse://user:pass@host:port/db?secure=1``).
Resolution order: ``--url`` flag > ``$CHSQL_URL`` env > the URL stored in the OS
keyring by ``chsql login``. Individual ``--host/--user/...`` flags override fields
for ad-hoc use. Built on stdlib ``argparse`` — no third-party CLI framework.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, parse_qs, unquote, urlparse, urlunparse

from . import __version__
from . import client as ch
from . import config as cfg
from . import errors
from .output import Format, emit

DEFAULT_MAX_ROWS = 100_000

_FORMATS = [f.value for f in Format]


# --------------------------------------------------------------------------- #
# connection (URL) helpers
# --------------------------------------------------------------------------- #
def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _url_to_conn(url: Optional[str]) -> Dict[str, object]:
    """Parse clickhouse://user:pass@host:port/db?secure=1&protocol=http into a dict."""
    if not url:
        return {}
    u = urlparse(url)
    q = parse_qs(u.query)
    conn: Dict[str, object] = {}
    if u.hostname:
        conn["host"] = u.hostname
    if u.port:
        conn["port"] = u.port
    if u.username:
        conn["user"] = unquote(u.username)
    if u.password is not None:
        conn["password"] = unquote(u.password)
    db = (u.path or "").strip("/")
    if db:
        conn["database"] = db
    secure: Optional[bool] = True if u.scheme in ("clickhouses", "https") else None
    if "secure" in q:
        secure = _truthy(q["secure"][0])
    if secure is not None:
        conn["secure"] = secure
    if "protocol" in q:
        conn["protocol"] = q["protocol"][0]
    return conn


def _resolve_url(args: argparse.Namespace) -> Optional[str]:
    return getattr(args, "url", None) or os.getenv("CHSQL_URL") or cfg.get_url()


def _conn_from(args: argparse.Namespace) -> Dict[str, object]:
    """URL (flag > $CHSQL_URL > keyring) with individual flags overriding fields."""
    base = _url_to_conn(_resolve_url(args))
    secure = args.secure if args.secure is not None else bool(base.get("secure", False))
    protocol = args.protocol if args.protocol != "auto" else (base.get("protocol") or "auto")
    return {
        "host": args.host or base.get("host"),
        "port": args.port or base.get("port"),
        "user": args.user or base.get("user"),
        "password": args.password if args.password is not None else base.get("password"),
        "secure": secure,
        "database": args.database or base.get("database"),
        "protocol": protocol,
    }


def _default_db(args: argparse.Namespace) -> str:
    if args.database:
        return args.database
    db = _url_to_conn(_resolve_url(args)).get("database")
    return str(db or "default")


def _mask_url(url: str) -> str:
    u = urlparse(url)
    if u.password is None:
        return url
    netloc = (u.username or "") + ":***@" + (u.hostname or "")
    if u.port:
        netloc += f":{u.port}"
    return urlunparse((u.scheme, netloc, u.path, u.params, u.query, u.fragment))


def _with_password(url: str, password: str) -> str:
    u = urlparse(url)
    userinfo = u.username or ""
    if password:
        userinfo += ":" + quote(password, safe="")
    netloc = userinfo + ("@" if userinfo else "") + (u.hostname or "")
    if u.port:
        netloc += f":{u.port}"
    return urlunparse((u.scheme, netloc, u.path, u.params, u.query, u.fragment))


# --------------------------------------------------------------------------- #
# misc helpers
# --------------------------------------------------------------------------- #
def _coerce(value: str):
    """Numeric-looking param values pass through unquoted so typed columns match."""
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _parse_params(pairs: List[str]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for item in pairs:
        key, sep, val = item.partition("=")
        if not sep:
            errors.fail(errors.QUERY_ERROR, f"bad --param (want key=value): {item!r}")
        out[key.strip()] = _coerce(val)
    return out


def _quote_ident(name: str) -> str:
    """Backtick-quote a SQL identifier, escaping embedded backticks."""
    return "`" + name.replace("`", "``") + "`"


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{label}{suffix}: ").strip()
    except EOFError:
        value = ""
    return value or default


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_query(args: argparse.Namespace) -> None:
    sql = args.sql if args.sql is not None else sys.stdin.read()
    if not sql.strip():
        errors.fail(errors.QUERY_ERROR, "empty query")

    kind = ch.classify(sql)
    if kind == "ddl" and not args.allow_ddl:
        errors.fail(errors.PERMISSION_ERROR,
                    "DDL blocked by read-only guard; pass --allow-ddl to run it")
    if kind == "write" and not args.write:
        errors.fail(errors.PERMISSION_ERROR,
                    "write blocked by read-only guard; pass --write to run it")

    params = _parse_params(args.param) if args.param else None
    max_rows = DEFAULT_MAX_ROWS if args.max_rows is None else args.max_rows
    client = ch.make_client(_conn_from(args))
    rows, columns = ch.run(client, sql, params=params,
                           settings=ch.row_cap_settings(max_rows))
    # Server-side cap bounds memory (~max_rows + one block); slice to exactly N.
    truncated = bool(max_rows) and len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    emit(rows, columns, args.format)
    if truncated:
        print(json.dumps({"warning": f"result truncated to {max_rows} rows; "
                                     "raise or disable with --max-rows (0 = unlimited)"},
                         ensure_ascii=False), file=sys.stderr)


def cmd_databases(args: argparse.Namespace) -> None:
    client = ch.make_client(_conn_from(args))
    rows, columns = ch.run(client, "SELECT name FROM system.databases ORDER BY name")
    emit(rows, columns, args.format)


def cmd_tables(args: argparse.Namespace) -> None:
    db = args.database_arg or _default_db(args)
    sql = ("SELECT name, engine, total_rows, total_bytes "
           "FROM system.tables WHERE database = %(db)s")
    params: Dict[str, object] = {"db": db}
    if args.like:
        sql += " AND name LIKE %(like)s"
        params["like"] = args.like
    if args.not_like:
        sql += " AND name NOT LIKE %(not_like)s"
        params["not_like"] = args.not_like
    sql += " ORDER BY name"

    client = ch.make_client(_conn_from(args))
    rows, columns = ch.run(client, sql, params=params)
    emit(rows, columns, args.format)


def cmd_describe(args: argparse.Namespace) -> None:
    table = args.table
    if "." in table:
        db, tbl = table.split(".", 1)
    else:
        db, tbl = _default_db(args), table

    # DESCRIBE TABLE works regardless of system.columns access filtering, and
    # raises a clean "unknown table" error (exit 1) when the table is missing.
    ident = f"{_quote_ident(db)}.{_quote_ident(tbl)}"
    client = ch.make_client(_conn_from(args))
    rows, columns = ch.run(client, f"DESCRIBE TABLE {ident}")

    names = [c[0] for c in columns]
    want = [("name", "name"), ("type", "type"),
            ("default_expression", "default"), ("comment", "comment")]
    idx = {src: names.index(src) for src, _ in want if src in names}
    out_cols = [(label, "String") for _, label in want]
    out_rows = [tuple(row[idx[src]] if src in idx else None for src, _ in want)
                for row in rows]
    emit(out_rows, out_cols, args.format)


def cmd_login(args: argparse.Namespace) -> None:
    if args.show:
        url = cfg.get_url()
        print(_mask_url(url) if url else "(not logged in)")
        return

    url = args.url_arg
    if not url:
        if not sys.stdin.isatty():
            errors.fail(errors.QUERY_ERROR, "no URL given")
        url = _prompt("Connection URL (clickhouse://user@host:port?secure=1)")
        if not url:
            errors.fail(errors.QUERY_ERROR, "no URL given")
        # Keep the password out of shell history: ask for it separately if absent.
        parsed = urlparse(url)
        if parsed.username and parsed.password is None:
            pw = getpass.getpass("Password (blank to skip): ")
            if pw:
                url = _with_password(url, pw)

    if not cfg.keyring_available():
        errors.fail(errors.CONNECTION_ERROR,
                    "no usable OS keyring on this system (common on headless servers/VPS). "
                    "Skip `chsql login` and set an env var instead: "
                    "export CHSQL_URL='clickhouse://user:pass@host:port?secure=1' — "
                    "then run chsql normally.")
    try:
        cfg.set_url(url)
    except Exception as exc:  # backend present but write failed (locked, etc.)
        errors.fail(errors.CONNECTION_ERROR,
                    f"could not write to the OS keyring ({exc}). "
                    "Alternative: export CHSQL_URL='<your url>' instead of `chsql login`.")
    print(f"logged in — stored {_mask_url(url)} in the OS keyring")
    print("try:  chsql databases")


def cmd_logout(args: argparse.Namespace) -> None:
    removed = cfg.delete_url()
    print("logged out (keyring entry removed)" if removed else "nothing to remove")


def _default_skill_dir() -> Path:
    """Default to the cross-agent skills dir (~/.agents/skills), which multiple
    agents read. Override via $SKILLS_DIR or --path."""
    env = os.getenv("SKILLS_DIR") or os.getenv("AGENT_SKILLS_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".agents" / "skills"


def cmd_skill_install(args: argparse.Namespace) -> None:
    try:
        from importlib.resources import files
        content = files("chsql.skill").joinpath("SKILL.md").read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        errors.fail(errors.QUERY_ERROR, f"cannot read bundled skill: {exc}")

    base = Path(args.path).expanduser() if args.path else _default_skill_dir()
    target = base / "chsql"
    target.mkdir(parents=True, exist_ok=True)
    dest = target / "SKILL.md"
    dest.write_text(content, encoding="utf-8")
    print(f"installed skill -> {dest}")


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def _add_format(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", "-f", type=Format, choices=list(Format),
                   default=Format.jsoneachrow, metavar="{%s}" % ",".join(_FORMATS),
                   help="Output format (default: jsoneachrow).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chsql",
        description="Agent-friendly ClickHouse query CLI (JSON-first, read-only by default).",
    )
    p.add_argument("--version", action="version", version=f"chsql {__version__}")
    p.add_argument("--url", help="Connection URL (overrides $CHSQL_URL and the stored login).")
    # Ad-hoc field overrides (no env defaults; the URL is the canonical source).
    p.add_argument("--host", help="Override host.")
    p.add_argument("--port", type=int, help="Override port.")
    p.add_argument("--protocol", choices=["auto", "native", "http"], default="auto",
                   help="Transport. auto: http for ports 443/8123/8443, else native.")
    p.add_argument("--user", "-u", help="Override user.")
    p.add_argument("--password", help="Override password.")
    p.add_argument("--secure", dest="secure", action="store_true", default=None,
                   help="Use TLS.")
    p.add_argument("--no-secure", dest="secure", action="store_false", help="Disable TLS.")
    p.add_argument("--database", "-d", help="Override default database.")

    sub = p.add_subparsers(dest="command")
    sub.required = True  # py3.9-compatible way to require a subcommand

    q = sub.add_parser("query", help="Run SQL (read-only unless --write/--allow-ddl).")
    q.add_argument("sql", nargs="?", help="SQL to run. Reads stdin if omitted.")
    q.add_argument("--param", "-p", action="append", default=[], metavar="KEY=VALUE",
                   help="Bind a value for %%(KEY)s in the SQL. Repeatable.")
    q.add_argument("--write", action="store_true", help="Allow INSERT/ALTER/DELETE/etc.")
    q.add_argument("--allow-ddl", action="store_true", help="Allow CREATE/DROP/TRUNCATE/etc.")
    q.add_argument("--max-rows", type=int, default=None, metavar="N",
                   help=f"Cap result rows server-side (default {DEFAULT_MAX_ROWS}; 0 = unlimited).")
    _add_format(q)
    q.set_defaults(func=cmd_query)

    d = sub.add_parser("databases", help="List databases.")
    _add_format(d)
    d.set_defaults(func=cmd_databases)

    t = sub.add_parser("tables", help="List tables with engine and row/byte counts.")
    t.add_argument("database_arg", nargs="?", metavar="DATABASE",
                   help="Database (default: connection database).")
    t.add_argument("--like", help="Keep tables whose name LIKE this.")
    t.add_argument("--not-like", dest="not_like", help="Drop tables whose name LIKE this.")
    _add_format(t)
    t.set_defaults(func=cmd_tables)

    de = sub.add_parser("describe", help="Show a table's columns (name, type, default, comment).")
    de.add_argument("table", help="Table name, optionally db.table.")
    _add_format(de)
    de.set_defaults(func=cmd_describe)

    lg = sub.add_parser("login", help="Store a connection URL in the OS keyring.")
    lg.add_argument("url_arg", nargs="?", metavar="URL",
                    help="clickhouse://user:pass@host:port/db?secure=1 (prompts if omitted).")
    lg.add_argument("--show", action="store_true", help="Print the stored URL (password masked).")
    lg.set_defaults(func=cmd_login)

    lo = sub.add_parser("logout", help="Remove the stored connection URL.")
    lo.set_defaults(func=cmd_logout)

    sk = sub.add_parser("skill", help="Manage the chsql agent skill.")
    sksub = sk.add_subparsers(dest="skill_command")
    sksub.required = True
    ski = sksub.add_parser("install", help="Install the bundled agent skill.")
    ski.add_argument("--path", help="Skills dir to install into (default: ~/.agents/skills).")
    ski.set_defaults(func=cmd_skill_install)

    return p


def app() -> None:
    """Console-script entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    app()
