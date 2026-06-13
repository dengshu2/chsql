# chsql

English · [简体中文](README.zh-CN.md)

Agent-friendly ClickHouse query CLI — **JSON-first, read-only by default,
semantic exit codes**. A thin wrapper over `clickhouse-driver` /
`clickhouse-connect` with **zero third-party CLI framework** (stdlib `argparse`).
Batteries included: native + HTTP transports and OS-keyring password storage all
work out of the box (~8 MB installed). Built for LLM agents to call over the
shell instead of standing up an MCP server.

## Install

Recommended — **uv** (puts `chsql` on your PATH globally):

```bash
uv tool install chsql                  # from PyPI (coming soon)
uv tool install -e /path/to/chsql      # from a local checkout (editable)
```

Or with **pipx**:

```bash
pipx install chsql
```

Then install the bundled agent skill (cross-agent path `~/.agents/skills`):

```bash
chsql skill install
```

## Use

```bash
chsql databases
chsql tables system --like '%part%'
chsql describe system.parts
chsql query "SELECT count() FROM system.tables"
```

Default output is **JSONEachRow** (NDJSON). Switch with
`--format json|table|csv|tsv`. Results are capped at 100k rows by default
(`--max-rows N`, `--max-rows 0` to disable).

### Connection

Flags or `CLICKHOUSE_*` env vars (same names as mcp-clickhouse, so migration is
zero-config). Flags win over env.

```
CLICKHOUSE_HOST  CLICKHOUSE_PORT  CLICKHOUSE_USER  CLICKHOUSE_PASSWORD
CLICKHOUSE_SECURE  CLICKHOUSE_DATABASE  CLICKHOUSE_PROTOCOL  CLICKHOUSE_PROFILE
```

```bash
# Public read-only playground (native protocol)
chsql --secure --host play.clickhouse.com --user explorer databases

# A server behind an HTTPS reverse proxy (HTTP interface on 443)
chsql --host ch.example.com --port 443 --secure databases   # auto -> http
```

### Config & credentials

Run `chsql config init` once to save a connection profile — then `chsql databases`
works with no flags. It follows the `gh` / AWS-CLI split: **non-secret settings**
go to `~/.config/chsql/config.ini`; the **password never does** — it goes to the
OS keyring (like `gh`) or behind a `password_command` (like AWS
`credential_process`).

```bash
# Interactive (asks only host/port/user/database + password backend)
chsql config init

# One-liner (no prompts): connection via flags, password from stdin into keyring
echo "$PASSWORD" | chsql config init --host ch.example.com --port 443 --secure \
  --user me --password-stdin

# Or seed from a URL
chsql config init --url 'clickhouse://me@ch.example.com:443?secure=1'

chsql config show     # inspect a profile (no secret shown)
chsql config path     # print config file path
chsql config edit     # open it in $EDITOR
chsql --profile prod databases   # use a named profile
```

Password resolution order: `--password` > `$CLICKHOUSE_PASSWORD` > OS keyring >
`password_command`. All other settings: flag > env var > profile > built-in default.

### Transport

| Protocol | Ports | Driver | When |
| --- | --- | --- | --- |
| `native` (default) | 9000 / 9440 | clickhouse-driver | direct TCP access |
| `http` | 8123 / 8443 / 443 | clickhouse-connect | HTTPS reverse-proxied servers |

`--protocol auto` (default) picks **http** for ports 443/8123/8443, else **native**.

### Agent contract

| Aspect | Behavior |
| --- | --- |
| Output | data → stdout (JSONEachRow by default); errors → stderr as `{"error","code"}` |
| Exit codes | `0` ok · `1` query error · `2` connection error · `3` write/DDL blocked |
| Safety | read-only by default; `--write` for DML, `--allow-ddl` for DDL; multi-statement aware |
| Limits | results capped at `--max-rows` (default 100k); truncation noted on stderr |
| Params | `--param k=v` bound as `%(k)s` (numeric values passed unquoted) |

## Commands

- `chsql query "<sql>"` — run SQL (reads stdin if no arg). Read-only unless `--write`/`--allow-ddl`.
- `chsql databases` — list databases.
- `chsql tables [db] --like ... --not-like ...` — list tables with engine and counts.
- `chsql describe <table|db.table>` — list columns (name, type, default, comment).
- `chsql config init|show|path|edit` — manage connection profiles.
- `chsql skill install [--path DIR]` — install the bundled agent skill.
- `chsql --version`

## Develop

```bash
pip install -e '.[dev]'
pytest
```

## License

MIT
