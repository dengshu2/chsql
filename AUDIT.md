# chsql Audit & Triage (v0.5.0)

A multi-agent review of `src/chsql` (~750 LoC): five reviewers across distinct
dimensions (correctness, error-handling, native↔http consistency, security,
CLI ergonomics), each finding adversarially verified by an independent agent that
re-read the code and defaulted to *reject*. 22 findings survived verification;
this document records which were acted on and — just as important — which were
deliberately **not**, and why.

Guiding principle: fix a finding only if it's a real bug **or** it protects one of
chsql's two core promises — *safe read-only by default* and *an agent-parseable
exit-code / stderr contract* — and the change earns its complexity.

## Fixed (11)

| Finding | Where | Fix |
| --- | --- | --- |
| Read-only guard misses destructive statements (`EXCHANGE`, `UNDROP`, `KILL`, `RESTORE`) — none lead with an obvious verb, so they classified as `read` | `client.py` `_DDL`/`_WRITE` | Added to the keyword sets (`EXCHANGE`/`UNDROP`→ddl, `KILL`/`RESTORE`→write) |
| No top-level exception handler — uncaught errors leak a raw traceback, breaking the JSON-error contract | `cli.py` `app()` | Wrap dispatch: `SystemExit` passes through, `BrokenPipeError`/`KeyboardInterrupt` handled, rest → `INTERNAL_ERROR` (exit 5) JSON. Native missing-driver also reported cleanly |
| Argparse usage errors exit 2 (plain text), colliding with `CONNECTION_ERROR=2` | `cli.py` `_Parser` | Subclass routes usage errors → `USAGE_ERROR` (exit 4) JSON |
| http backend misclassifies server-reported connection/auth failures as `QUERY_ERROR`/exit 1 | `client.py` `_HttpClient.query` | Parse `Code:` from `DatabaseError`; route `_CONNECTION_CODES` → `CONNECTION_ERROR`/exit 2 + `clickhouse_code`, matching native |
| Negative `--max-rows` silently drops the last row + bogus warning | `cli.py` `cmd_query` | Normalize once: `<= 0` means unlimited on both server and client side |
| `https://`/`http://` URL never implies HTTP transport — resolves to native TCP | `cli.py` `_url_to_conn` | Scheme implies `protocol=http` unless `?protocol=` overrides |
| Duplicate column names collapse in `json`/`jsoneachrow` (silent data loss) | `output.py` `_dedupe` | Disambiguate keys (`a`, `a_1`, …); no-op when already unique |
| `csv`/`tsv` render NULL and empty-string identically | `output.py` `_cell` | Emit `\N` (ClickHouse TSV/CSV convention) for NULL |
| No way to bound a runaway query | `cli.py` `--timeout` | Opt-in flag → socket read timeout + server `max_execution_time` |
| Malformed URL (bad port) crashes with a raw `ValueError` | `cli.py` `_url_to_conn` | Guard `u.port` → clean `QUERY_ERROR` JSON |
| `skill install` mkdir/write unguarded → raw `OSError` | `cli.py` `cmd_skill_install` | Wrap in `try/except OSError` → JSON error |

New exit codes (additive, existing 0–3 unchanged): `USAGE_ERROR=4`, `INTERNAL_ERROR=5`.

## Rejected (11) — and why

- **Default query timeout.** A hard default would silently kill legitimate long
  analytical queries — the opposite of useful for an analytics CLI. Shipped as
  opt-in `--timeout` instead; the driver's 300s default still applies otherwise.
- **Keyring failures swallowed by `get_url()`/`delete_url()`.** Intentional
  graceful degradation: a locked/absent keychain should not make every command
  fail. Surfacing the raw backend error would be a regression, not a fix.
- **Auto-retry on transient connection errors.** An agent driving the CLI can
  retry itself; in-process retry/backoff adds state and surprise for little gain.
- **`--password` visible in process argv.** Inherent to any password-on-argv CLI;
  already mitigated by `$CHSQL_URL` and the keyring login flow. `--password-stdin`
  would be scope creep.
- **`jsoneachrow` emits zero bytes on an empty result.** With the new top-level
  handler, `exit 0` + empty stdout is now unambiguously "0 rows" (a crash exits
  non-zero with JSON on stderr). Empty NDJSON for an empty result is correct.
- **Cosmetic native↔http divergences** (row container list vs tuple, column-type
  string spelling, eager vs lazy connection timing, prose success messages on
  stdout, no `--quiet`, table-format escaping). Real observations, but no data or
  exit-code impact — not worth the churn or the behavior change.

## Verification

`pytest` (28 tests, incl. new coverage for the guard keywords, URL scheme/port
handling, duplicate-column dedupe, and NULL sentinel) + live CLI smoke tests of
every structured-error exit path (4 usage, 3 permission, 2 connection over both
backends, 1 bad-port).
