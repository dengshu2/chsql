# Changelog

## 0.5.0

- **Read-only guard** now blocks `EXCHANGE`/`UNDROP` (DDL) and `KILL`/`RESTORE`
  (write) — destructive statements that don't lead with an obvious verb and
  previously classified as `read`.
- **Every exit path honors the agent contract.** A top-level handler converts any
  unexpected error into structured stderr JSON (`INTERNAL_ERROR`, exit 5) instead
  of a raw traceback, handles `BrokenPipeError` (`… | head`) cleanly, and gives
  native a clear message when `clickhouse-driver` is missing. Argparse usage
  errors now emit JSON with a dedicated code (`USAGE_ERROR`, exit 4) instead of
  plain text + exit 2, which collided with `CONNECTION_ERROR`.
- **http backend** now routes server-reported connection/auth failures (codes
  32/209/210/516/519) to `CONNECTION_ERROR`/exit 2 and includes `clickhouse_code`,
  matching the native backend instead of mislabeling them `QUERY_ERROR`/exit 1.
- **`https://` / `http://` URLs imply HTTP transport** so `https://host` (no port)
  no longer silently resolves to the native TCP port.
- **`--timeout SECONDS`** bounds a query (socket read + server `max_execution_time`).
- Fixes: negative `--max-rows` no longer drops the last row; duplicate column
  names in `json`/`jsoneachrow` are disambiguated instead of silently collapsing;
  `csv`/`tsv` emit `\N` for NULL (distinct from an empty string); a malformed
  connection URL (bad port) and a failed `skill install` write report clean JSON
  errors instead of tracebacks.

## 0.4.1

- `chsql login` now detects a missing/unusable OS keyring (common on headless
  servers/VPS) and points to the `$CHSQL_URL` env var instead of failing with a
  cryptic backend error.
- Document the connection URL query params (`secure`, `protocol`) and the
  headless-server workflow in the READMEs and the agent skill.

## 0.4.0

- **One connection model: a URL.** `clickhouse://user:pass@host:port/db?secure=1`,
  resolved as `--url` > `$CHSQL_URL` > the URL stored by `chsql login` (OS keyring).
- New `chsql login [URL]` / `chsql logout` / `chsql login --show`.
- **Removed** (breaking): `chsql config init/show/path/edit`, the
  `~/.config/chsql/config.ini` profile file, `password_command`, named
  `--profile`, and the `CLICKHOUSE_*` per-field env vars. Individual
  `--host/--user/...` flags remain as ad-hoc overrides.
- URL passwords are percent-decoded; `login` keeps the password out of shell
  history by prompting separately when the URL omits it.

## 0.3.0

- **Batteries included**: `clickhouse-connect` (HTTP transport) and `keyring`
  are now core dependencies. Install is just `uv tool install chsql` /
  `pipx install chsql` — no `[http,keyring]` extras needed (~8 MB).
- **Simpler `config init`**: non-interactive flags (`--host/--port/--user/
  --secure/--database`), `--url` seeding, `--password-stdin` /
  `--password-command`. Interactive mode drops the protocol/secure prompts
  (both inferred from the port).
- **New commands**: `chsql --version`, `chsql config path`, `chsql config edit`.
- **Result-size safety**: results are capped at `--max-rows` (default 100k)
  server-side, sliced to exactly N client-side, with a truncation notice on
  stderr. `--max-rows 0` disables.
- **Read-only guard hardening**: every `;`-separated statement is classified, so
  `SELECT 1; DROP TABLE x` can't slip past the guard.
- Single-source version (hatch reads `__init__.py`).

## 0.2.0

- Config profiles + credential management: `config init` / `config show`,
  `--profile`, OS keyring / `password_command` backends.
- HTTP transport via `clickhouse-connect`; `--protocol auto/native/http`.

## 0.1.0

- Initial release: `query` / `databases` / `tables` / `describe`, JSON-first
  output, semantic exit codes, read-only guard, bundled agent skill.
