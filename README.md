# chsql

English · [简体中文](README.zh-CN.md)

Agent-friendly ClickHouse query CLI — **JSON-first, read-only by default,
semantic exit codes**. A thin wrapper over `clickhouse-driver` /
`clickhouse-connect` with **zero third-party CLI framework** (stdlib `argparse`).
Batteries included: native + HTTP transports and OS-keyring password storage all
work out of the box (~8 MB installed). Built for LLM agents to call over the
shell instead of standing up an MCP server.

## Install

```bash
uv tool install chsql     # recommended (puts chsql on your PATH)
# or
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

### Connection — one URL

A connection is a single URL:

```
clickhouse://user:password@host:port/database?secure=1
```

`chsql login` stores it in the **OS keyring** (the password never touches a
config file) — then everything just works with no flags:

```bash
chsql login 'clickhouse://me:pw@ch.example.com:443?secure=1'   # paste once
chsql databases                                                # zero-config
chsql login --show     # print the stored URL (password masked)
chsql logout           # remove it
```

Resolution order: `--url` flag > `$CHSQL_URL` env > the stored login. Individual
`--host/--port/--user/--password/--secure/--protocol/--database` flags override
fields for one-off use:

```bash
# Public read-only playground — no login needed
chsql --host play.clickhouse.com --user explorer --secure databases
```

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
- `chsql login [URL] | logout | login --show` — manage the stored connection.
- `chsql skill install [--path DIR]` — install the bundled agent skill.
- `chsql --version`

## Develop

```bash
pip install -e '.[dev]'
pytest
```

## License

MIT
