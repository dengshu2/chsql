# Changelog

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
