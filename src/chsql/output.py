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


def _scalar(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def emit(rows: Sequence[tuple], columns: List[Tuple[str, str]], fmt: Format,
         out=sys.stdout) -> None:
    names = [c[0] for c in columns]
    types = [c[1] for c in columns]

    if fmt == Format.jsoneachrow:
        for row in rows:
            out.write(json.dumps(dict(zip(names, row)), ensure_ascii=False, default=str))
            out.write("\n")

    elif fmt == Format.json:
        payload = {
            "meta": [{"name": n, "type": t} for n, t in zip(names, types)],
            "data": [dict(zip(names, row)) for row in rows],
            "rows": len(rows),
        }
        out.write(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
        out.write("\n")

    elif fmt in (Format.csv, Format.tsv):
        delimiter = "," if fmt == Format.csv else "\t"
        writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
        writer.writerow(names)
        for row in rows:
            writer.writerow([_scalar(v) for v in row])

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
