---
name: chsql-clickhouse
description: >-
  Query ClickHouse from the shell with the `chsql` CLI. Use whenever the user
  wants to read data from ClickHouse, explore databases/tables/schema, or run a
  SQL analysis against a ClickHouse server. Triggers: ClickHouse, 查 ClickHouse,
  跑个 SQL, 看下这个表, explore tables, run a query.
---

# chsql — querying ClickHouse

`chsql` is a small CLI for querying ClickHouse. It is JSON-first and read-only
by default, so it is safe to call for exploration without risking writes.

## When to use

The user wants to read from ClickHouse, list databases/tables, inspect a table's
schema, or run a SELECT for analysis. Do **not** use it to mutate data unless the
user explicitly asks — and even then, pass the explicit safety flag.

## Workflow — discover before you query

Don't guess table or column names. Discover them first:

1. `chsql databases` — list databases.
2. `chsql tables [DB] --like '%keyword%'` — list tables (name, engine, rows).
3. `chsql describe <table>` — list a table's columns (name, type, default, comment).
4. `chsql query "SELECT ..."` — run the query once you know the schema.

`describe` accepts `db.table` or a bare table name (uses the default database).

## Reading the output

- **stdout** carries the data. Default format is **JSONEachRow** — one JSON
  object per line (NDJSON); parse it line by line.
- Other formats: `--format json` (single object with `meta`/`data`/`rows`),
  `--format table` (human-readable), `--format csv`, `--format tsv`.
- **stderr** carries errors as a single JSON object: `{"error": ..., "code": ...}`.
- Results are capped at 100k rows by default. A `{"warning": ...}` line on stderr
  means the result was truncated — re-run with `--max-rows N` (or `--max-rows 0`
  for no cap) if you need the rest, but prefer adding `LIMIT`/filters to the SQL.

## Branch on the exit code, not on text

- `0` success
- `1` query error (bad SQL / server rejected it) — read stderr, fix the SQL
- `2` connection error (host/credentials/network) — check connection settings
- `3` permission blocked (a write/DDL hit the read-only guard) — see below

## Safety — read-only by default

Plain `chsql query "..."` allows only reads (SELECT/SHOW/DESCRIBE/EXPLAIN/WITH).
Writes and DDL are blocked with exit code `3` unless the user explicitly wants them:

- `--write` allows INSERT / ALTER / DELETE / UPDATE / OPTIMIZE / SYSTEM.
- `--allow-ddl` allows CREATE / DROP / TRUNCATE / RENAME.

Only add these flags when the user explicitly asked to modify data or schema.

## Parameterized queries (prefer this over string-building)

Bind values with `--param KEY=VALUE` and reference them as `%(KEY)s` in the SQL.
Numeric-looking values are passed unquoted so typed columns match.

```bash
chsql query --param id=123 "SELECT * FROM events WHERE id = %(id)s LIMIT 10"
```

## Connection

A connection is a single URL:
`clickhouse://user:password@host:port/database?secure=1`. Resolution order:
`--url` flag > `$CHSQL_URL` env > the URL stored by `chsql login` (in the OS
keyring). Individual `--host/--port/--user/--password/--secure/--protocol/
--database` flags override fields for ad-hoc use.

If the user has run `chsql login`, plain `chsql databases` / `chsql query "..."`
just work with **no connection flags**. For a one-off connection (e.g. the public
playground) pass flags or a URL directly:

```bash
chsql --host play.clickhouse.com --user explorer --secure databases
chsql --url 'clickhouse://explorer@play.clickhouse.com:9440?secure=1' databases
```

### Transport: native vs http

- **native** (default) — fast TCP protocol, ports 9000 / 9440 (secure).
- **http** — the HTTP(S) interface, ports 8123 / 8443 / 443. Use this when the
  server is behind an HTTPS reverse proxy that only exposes the HTTP interface
  (a very common deployment).

`--protocol auto` (the default), or `?protocol=` in the URL, picks **http** for
ports 443/8123/8443 and **native** otherwise. If a connection to an HTTPS
endpoint times out with exit code 2, it is almost certainly an HTTP-only server —
add `?protocol=http` to the URL (or point the port at 443/8443).

## Recipes

```bash
# Row count
chsql query "SELECT count() FROM system.numbers LIMIT 1000000"

# Top-N as a readable table
chsql query --format table "SELECT name, engine FROM system.tables LIMIT 10"

# Inspect a table before writing SQL against it
chsql describe system.parts

# Connect to the public ClickHouse playground (read-only demo data)
chsql --secure --host play.clickhouse.com --user explorer databases
```
