import argparse

from chsql import cli
from chsql import config as cfg

_ENV = ("CLICKHOUSE_HOST", "CLICKHOUSE_PORT", "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD", "CLICKHOUSE_SECURE", "CLICKHOUSE_DATABASE",
        "CLICKHOUSE_PROTOCOL")


def _args(**kw):
    base = dict(host=None, port=None, user=None, password=None, secure=None,
                database=None, protocol="auto", profile="default")
    base.update(kw)
    return argparse.Namespace(**base)


def test_write_and_load_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg.write_profile("default", {"host": "h", "port": "443", "protocol": "http"})
    p = cfg.load_profile("default")
    assert p["host"] == "h" and p["port"] == "443" and p["protocol"] == "http"
    assert cfg.load_profile("missing") == {}


def test_multiple_profiles_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg.write_profile("default", {"host": "a"})
    cfg.write_profile("prod", {"host": "b"})
    assert cfg.load_profile("default")["host"] == "a"
    assert cfg.load_profile("prod")["host"] == "b"


def test_password_command(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfg.run_password_command("printf secret123") == "secret123"
    assert cfg.run_password_command("exit 3") is None


def test_value_with_percent_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg.write_profile("default", {"password_command": "echo 100%done"})
    assert cfg.load_profile("default")["password_command"] == "echo 100%done"


def test_conn_from_uses_config(tmp_path, monkeypatch):
    for v in _ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(cfg, "get_keyring_password", lambda u, h: None)
    cfg.write_profile("default", {
        "host": "ch.example", "port": "443", "protocol": "http", "secure": "true",
        "user": "bob", "database": "mydb", "password_command": "printf pw42",
    })
    conn = cli._conn_from(_args())
    assert conn["host"] == "ch.example" and conn["port"] == 443
    assert conn["protocol"] == "http" and conn["secure"] is True
    assert conn["user"] == "bob" and conn["database"] == "mydb"
    assert conn["password"] == "pw42"  # keyring empty -> password_command


def test_flag_overrides_config(tmp_path, monkeypatch):
    for v in _ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(cfg, "get_keyring_password", lambda u, h: None)
    cfg.write_profile("default", {"host": "fromconfig", "secure": "true"})
    conn = cli._conn_from(_args(host="fromflag", secure=False))
    assert conn["host"] == "fromflag"
    assert conn["secure"] is False  # explicit --no-secure beats config


def test_parse_url():
    settings, pw = cli._parse_url("clickhouse://alice:secret@h.example:9440/mydb?secure=1")
    assert settings["host"] == "h.example" and settings["port"] == "9440"
    assert settings["user"] == "alice" and settings["database"] == "mydb"
    assert settings["secure"] == "1" and pw == "secret"


def test_config_init_non_interactive(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    args = argparse.Namespace(
        profile="default", url=None, host="ch.example", port=443, user="bob",
        database="db", secure=None, password_stdin=False,
        password_command="printf pw", non_interactive=True)
    cli.cmd_config_init(args)
    p = cfg.load_profile("default")
    assert p["host"] == "ch.example" and p["port"] == "443" and p["user"] == "bob"
    assert p["secure"] == "true"  # inferred from port 443
    assert p["password_command"] == "printf pw"
    assert "password" not in p  # never the raw secret
