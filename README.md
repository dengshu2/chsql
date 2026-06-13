# chsql

Agent-friendly ClickHouse query CLI — **JSON-first, read-only by default,
semantic exit codes**. A thin wrapper over `clickhouse-driver`, with **zero
third-party CLI dependencies** (stdlib `argparse`) — ~3.5 MB installed assuming
Python is present. Built for LLM agents to call over the shell instead of
standing up an MCP server.

## Install

```bash
pipx install chsql          # native protocol only (lightest)
pipx install 'chsql[http]'  # + HTTP(S) interface support (proxied servers)
chsql skill install         # drop the agent SKILL.md into your skills dir
```

## Use

```bash
chsql databases
chsql tables system --like '%part%'
chsql describe system.parts
chsql query "SELECT count() FROM system.tables"
```

Default output is **JSONEachRow** (NDJSON). Switch with
`--format json|table|csv|tsv`.

### Connection

Flags or `CLICKHOUSE_*` env vars (same names as mcp-clickhouse, so migration is
zero-config). Flags win over env.

```
CLICKHOUSE_HOST  CLICKHOUSE_PORT  CLICKHOUSE_USER
CLICKHOUSE_PASSWORD  CLICKHOUSE_SECURE  CLICKHOUSE_DATABASE
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
go to `~/.config/chsql/config.ini`; the **password never does**. Store the
password in the OS keyring (`pip install 'chsql[keyring]'`, like `gh`) or point a
`password_command` at it (like AWS `credential_process`).

```bash
chsql config init                 # interactive: writes the default profile
chsql config show                 # inspect a profile (no secret shown)
chsql --profile prod databases    # use a named profile
```

Password resolution order: `--password` > `$CLICKHOUSE_PASSWORD` > OS keyring >
`password_command`. All other settings: flag > env var > profile > built-in default.

### Transport

| Protocol | Ports | Driver | When |
| --- | --- | --- | --- |
| `native` (default) | 9000 / 9440 | clickhouse-driver | direct TCP access |
| `http` | 8123 / 8443 / 443 | clickhouse-connect (`chsql[http]`) | HTTPS reverse-proxied servers |

`--protocol auto` (default) picks **http** for ports 443/8123/8443, else **native**.

### Agent contract

| Aspect | Behavior |
| --- | --- |
| Output | data → stdout (JSONEachRow by default); errors → stderr as `{"error","code"}` |
| Exit codes | `0` ok · `1` query error · `2` connection error · `3` write/DDL blocked |
| Safety | read-only by default; `--write` for DML, `--allow-ddl` for DDL |
| Params | `--param k=v` bound as `%(k)s` (numeric values passed unquoted) |

## Commands

- `chsql query "<sql>"` — run SQL (reads stdin if no arg). Read-only unless `--write`/`--allow-ddl`.
- `chsql databases` — list databases.
- `chsql tables [db] --like ... --not-like ...` — list tables with engine and counts.
- `chsql describe <table|db.table>` — list columns (name, type, default, comment).
- `chsql skill install [--path DIR]` — install the bundled agent skill.

## Develop

```bash
pip install -e '.[dev]'
pytest
```
