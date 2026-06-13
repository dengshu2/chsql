import argparse

from chsql import cli
from chsql import config as cfg


def _args(**kw):
    base = dict(url=None, host=None, port=None, user=None, password=None,
                secure=None, database=None, protocol="auto")
    base.update(kw)
    return argparse.Namespace(**base)


def test_url_to_conn():
    c = cli._url_to_conn("clickhouse://bob:pw@h.example:443/mydb?secure=1&protocol=http")
    assert c["host"] == "h.example" and c["port"] == 443 and c["user"] == "bob"
    assert c["password"] == "pw" and c["database"] == "mydb"
    assert c["secure"] is True and c["protocol"] == "http"


def test_url_scheme_implies_secure():
    assert cli._url_to_conn("clickhouses://h")["secure"] is True
    assert "secure" not in cli._url_to_conn("clickhouse://h")
    assert cli._url_to_conn("") == {}


def test_password_percent_decoding_roundtrips():
    built = cli._with_password("clickhouse://u@h:443?secure=1", "p@ss:word")
    c = cli._url_to_conn(built)
    assert c["user"] == "u" and c["password"] == "p@ss:word" and c["secure"] is True


def test_conn_from_env_url(monkeypatch):
    monkeypatch.setattr(cfg, "get_url", lambda: None)
    monkeypatch.setenv("CHSQL_URL", "clickhouse://u:p@host:443?secure=1")
    conn = cli._conn_from(_args())
    assert conn["host"] == "host" and conn["port"] == 443 and conn["user"] == "u"
    assert conn["password"] == "p" and conn["secure"] is True


def test_conn_from_keyring(monkeypatch):
    monkeypatch.delenv("CHSQL_URL", raising=False)
    monkeypatch.setattr(cfg, "get_url", lambda: "clickhouse://k@kh:9440?secure=1")
    conn = cli._conn_from(_args())
    assert conn["host"] == "kh" and conn["user"] == "k" and conn["secure"] is True


def test_flag_overrides_url(monkeypatch):
    monkeypatch.delenv("CHSQL_URL", raising=False)
    monkeypatch.setattr(cfg, "get_url", lambda: "clickhouse://u:p@host:443?secure=1")
    conn = cli._conn_from(_args(host="other", secure=False))
    assert conn["host"] == "other" and conn["secure"] is False
    assert conn["user"] == "u"  # untouched fields still come from the URL


def test_mask_url():
    assert cli._mask_url("clickhouse://u:secret@h:443") == "clickhouse://u:***@h:443"
    assert cli._mask_url("clickhouse://u@h:443") == "clickhouse://u@h:443"
