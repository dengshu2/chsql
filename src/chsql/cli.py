"""chsql — Agent-friendly ClickHouse query CLI.

Subcommands: query, databases, tables, describe, skill install.

Built on the standard-library ``argparse`` (no third-party CLI framework) so the
only runtime dependency is ``clickhouse-driver`` — the whole point is to stay
genuinely light.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import client as ch
from . import config as cfg
from . import errors
from .output import Format, emit

_FORMATS = [f.value for f in Format]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _env_bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(value: Optional[str]) -> Optional[int]:
    return int(value) if value not in (None, "") else None


def _conn_from(args: argparse.Namespace) -> Dict[str, object]:
    """Merge CLI flags > env (already in args) > config profile, then resolve the
    password (flag/env > keyring > password_command)."""
    profile = cfg.load_profile(getattr(args, "profile", None) or "default")

    host = args.host or profile.get("host")
    port = args.port or (int(profile["port"]) if profile.get("port") else None)
    user = args.user or profile.get("user")
    database = args.database or profile.get("database")
    protocol = args.protocol if args.protocol != "auto" else (profile.get("protocol") or "auto")

    secure = args.secure
    if secure is None:
        env = os.getenv("CLICKHOUSE_SECURE")
        if env is not None:
            secure = _env_bool(env)
        elif "secure" in profile:
            secure = _env_bool(profile.get("secure"))
        else:
            secure = False

    password = args.password
    if not password:
        password = cfg.get_keyring_password(user or "default", host or "localhost")
    if not password and profile.get("password_command"):
        password = cfg.run_password_command(profile["password_command"])

    return dict(host=host, port=port, user=user, password=password,
                secure=secure, database=database, protocol=protocol)


def _default_db(args: argparse.Namespace) -> str:
    profile = cfg.load_profile(getattr(args, "profile", None) or "default")
    return str(args.database or profile.get("database") or "default")


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
    client = ch.make_client(_conn_from(args))
    rows, columns = ch.run(client, sql, params=params)
    emit(rows, columns, args.format)


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

    # Project the verbose DESCRIBE output down to the agent-useful columns.
    names = [c[0] for c in columns]
    want = [("name", "name"), ("type", "type"),
            ("default_expression", "default"), ("comment", "comment")]
    idx = {src: names.index(src) for src, _ in want if src in names}
    out_cols = [(label, "String") for _, label in want]
    out_rows = [tuple(row[idx[src]] if src in idx else None for src, _ in want)
                for row in rows]
    emit(out_rows, out_cols, args.format)


def _default_skill_dir() -> Path:
    """Where to install the skill. Defaults to the cross-agent skills dir
    (~/.agents/skills), which multiple agents read. Override via $SKILLS_DIR
    or --path (e.g. ~/.claude/skills for Claude Code only)."""
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


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{label}{suffix}: ").strip()
    except EOFError:
        value = ""
    return value or default


def _prompt_bool(label: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    value = _prompt(f"{label} ({hint})")
    if not value:
        return default
    return value.lower() in ("y", "yes", "1", "true", "on")


def cmd_config_init(args: argparse.Namespace) -> None:
    name = args.profile or "default"
    print(f"Configuring chsql profile '{name}'. Press Enter to accept the [default].\n")
    host = _prompt("Host", "localhost")
    protocol = _prompt("Protocol (auto/native/http)", "auto")
    port = _prompt("Port (blank = protocol default)", "")
    secure = _prompt_bool("Use TLS (secure)?", False)
    user = _prompt("User", "default")
    database = _prompt("Database", "default")

    settings: Dict[str, str] = {
        "host": host, "protocol": protocol, "user": user, "database": database,
        "secure": "true" if secure else "false",
    }
    if port.strip():
        settings["port"] = port.strip()

    print("\nPassword storage (the password is never written to the config file):")
    if cfg.keyring_available():
        choice = _prompt("  [k] OS keyring   [c] password command   [s] skip", "k").lower()
    else:
        print("  keyring not installed — for OS keychain run: pip install 'chsql[keyring]'")
        choice = _prompt("  [c] password command   [s] skip", "s").lower()

    if choice.startswith("k") and cfg.keyring_available():
        pw = getpass.getpass("  Password (stored in OS keyring): ")
        if pw:
            cfg.set_keyring_password(user, host, pw)
            print(f"  stored in keyring (service=chsql, account={user}@{host})")
    elif choice.startswith("c"):
        command = _prompt("  Password command (run at query time, e.g. "
                          "security find-generic-password -s chsql -a USER -w)")
        if command.strip():
            settings["password_command"] = command.strip()

    path = cfg.write_profile(name, settings)
    print(f"\nwrote {path}")
    hint = "chsql databases" if name == "default" else f"chsql --profile {name} databases"
    print(f"try:  {hint}")


def cmd_config_show(args: argparse.Namespace) -> None:
    import json
    name = args.profile or "default"
    profile = cfg.load_profile(name)
    if not profile:
        errors.fail(errors.QUERY_ERROR,
                    f"no such profile: {name} (config file: {cfg.config_file()})")
    info = dict(profile)
    info["_password_in_keyring"] = cfg.get_keyring_password(
        profile.get("user", "default"), profile.get("host", "localhost")) is not None
    info["_config_file"] = str(cfg.config_file())
    print(json.dumps({name: info}, ensure_ascii=False, indent=2))


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
    p.add_argument("--host", default=os.getenv("CLICKHOUSE_HOST"),
                   help="Server host (default: localhost). [env: CLICKHOUSE_HOST]")
    p.add_argument("--port", type=int, default=_env_int(os.getenv("CLICKHOUSE_PORT")),
                   help="Port. Default by protocol: native 9000/9440, http 8123/8443. "
                        "[env: CLICKHOUSE_PORT]")
    p.add_argument("--protocol", choices=["auto", "native", "http"],
                   default=os.getenv("CLICKHOUSE_PROTOCOL") or "auto",
                   help="Transport. auto: http for ports 443/8123/8443, else native. "
                        "[env: CLICKHOUSE_PROTOCOL]")
    p.add_argument("--user", "-u", default=os.getenv("CLICKHOUSE_USER"),
                   help="User (default: default). [env: CLICKHOUSE_USER]")
    p.add_argument("--password", default=os.getenv("CLICKHOUSE_PASSWORD"),
                   help="Password. [env: CLICKHOUSE_PASSWORD]")
    p.add_argument("--secure", dest="secure", action="store_true", default=None,
                   help="Use TLS (native secure port 9440). [env: CLICKHOUSE_SECURE]")
    p.add_argument("--no-secure", dest="secure", action="store_false",
                   help="Disable TLS.")
    p.add_argument("--database", "-d", default=os.getenv("CLICKHOUSE_DATABASE"),
                   help="Default database (default: default). [env: CLICKHOUSE_DATABASE]")
    p.add_argument("--profile", default=os.getenv("CLICKHOUSE_PROFILE") or "default",
                   help="Config profile from ~/.config/chsql/config.ini. "
                        "[env: CLICKHOUSE_PROFILE]")

    sub = p.add_subparsers(dest="command")
    sub.required = True  # py3.9-compatible way to require a subcommand

    q = sub.add_parser("query", help="Run SQL (read-only unless --write/--allow-ddl).")
    q.add_argument("sql", nargs="?", help="SQL to run. Reads stdin if omitted.")
    q.add_argument("--param", "-p", action="append", default=[], metavar="KEY=VALUE",
                   help="Bind a value for %%(KEY)s in the SQL. Repeatable.")
    q.add_argument("--write", action="store_true", help="Allow INSERT/ALTER/DELETE/etc.")
    q.add_argument("--allow-ddl", action="store_true", help="Allow CREATE/DROP/TRUNCATE/etc.")
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

    sk = sub.add_parser("skill", help="Manage the chsql agent skill.")
    sksub = sk.add_subparsers(dest="skill_command")
    sksub.required = True
    ski = sksub.add_parser("install", help="Install the bundled agent skill.")
    ski.add_argument("--path", help="Skills dir to install into (default: ~/.agents/skills).")
    ski.set_defaults(func=cmd_skill_install)

    cf = sub.add_parser("config", help="Manage connection config profiles.")
    cfsub = cf.add_subparsers(dest="config_command")
    cfsub.required = True
    cfi = cfsub.add_parser("init", help="Interactively create/update a profile.")
    cfi.set_defaults(func=cmd_config_init)
    cfs = cfsub.add_parser("show", help="Show a profile (no secrets stored in the file).")
    cfs.set_defaults(func=cmd_config_show)

    return p


def app() -> None:
    """Console-script entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    app()
