"""Output formatters. Default is JSONEachRow (NDJSON) for easy agent parsing."""

from __future__ import annotations

import csv
import json
import sys
from enum import Enum
from typing import List, Sequence, Tuple


class Format(str, Enum):
    jsoneachrow = "jsoneachrow"
    json = "json"
    table = "table"
    csv = "csv"
    tsv = "tsv"


# NULL marker for the delimited formats — matches ClickHouse's own TSV/CSV
# convention and keeps a real NULL distinguishable from an empty string.
_NULL = "\\N"


def _scalar(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _cell(value) -> str:
    if value is None:
        return _NULL
    return value if isinstance(value, str) else str(value)


def _dedupe(names: List[str]) -> List[str]:
    """Make column names unique so a dict-keyed row can't silently drop a column
    (e.g. ``SELECT a, a`` or an unaliased self-join). No-op when already unique."""
    if len(set(names)) == len(names):
        return names
    seen: dict = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def emit(rows: Sequence[tuple], columns: List[Tuple[str, str]], fmt: Format,
         out=sys.stdout) -> None:
    names = [c[0] for c in columns]
    types = [c[1] for c in columns]

    if fmt == Format.jsoneachrow:
        keys = _dedupe(names)
        for row in rows:
            out.write(json.dumps(dict(zip(keys, row)), ensure_ascii=False, default=str))
            out.write("\n")

    elif fmt == Format.json:
        keys = _dedupe(names)
        payload = {
            "meta": [{"name": n, "type": t} for n, t in zip(keys, types)],
            "data": [dict(zip(keys, row)) for row in rows],
            "rows": len(rows),
        }
        out.write(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
        out.write("\n")

    elif fmt in (Format.csv, Format.tsv):
        delimiter = "," if fmt == Format.csv else "\t"
        writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
        writer.writerow(names)
        for row in rows:
            writer.writerow([_cell(v) for v in row])

    elif fmt == Format.table:
        _emit_table(names, rows, out)

    else:  # pragma: no cover - guarded by the enum
        raise ValueError(f"unknown format: {fmt}")


def _emit_table(names: List[str], rows: Sequence[tuple], out) -> None:
    cells = [[_scalar(v) for v in row] for row in rows]
    widths = [len(n) for n in names]
    for row in cells:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))

    def line(values):
        return " | ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    out.write(line(names) + "\n")
    out.write("-+-".join("-" * w for w in widths) + "\n")
    for row in cells:
        out.write(line(row) + "\n")
