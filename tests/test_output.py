import io
import json

from chsql.output import Format, emit

COLUMNS = [("id", "UInt64"), ("name", "String")]
ROWS = [(1, "alice"), (2, "bob"), (3, None)]


def _run(fmt):
    buf = io.StringIO()
    emit(ROWS, COLUMNS, fmt, out=buf)
    return buf.getvalue()


def test_jsoneachrow():
    lines = _run(Format.jsoneachrow).strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0]) == {"id": 1, "name": "alice"}
    assert json.loads(lines[2]) == {"id": 3, "name": None}


def test_json_envelope():
    payload = json.loads(_run(Format.json))
    assert payload["rows"] == 3
    assert payload["meta"][0] == {"name": "id", "type": "UInt64"}
    assert payload["data"][1] == {"id": 2, "name": "bob"}


def test_csv():
    out = _run(Format.csv).splitlines()
    assert out[0] == "id,name"
    assert out[1] == "1,alice"
    assert out[3] == "3,"  # None -> empty cell


def test_table():
    out = _run(Format.table)
    assert "id" in out and "name" in out and "alice" in out
