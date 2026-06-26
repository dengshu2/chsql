import pytest

from chsql import cli


def test_https_scheme_implies_http_transport():
    c = cli._url_to_conn("https://h.example/mydb")
    assert c["protocol"] == "http" and c["secure"] is True
    # No port given: protocol hint (not the port) is what steers transport.
    assert "port" not in c


def test_explicit_protocol_query_wins_over_scheme():
    c = cli._url_to_conn("https://h/db?protocol=native")
    assert c["protocol"] == "native"


def test_clickhouse_scheme_leaves_protocol_unset():
    assert "protocol" not in cli._url_to_conn("clickhouse://h:9000/db")


def test_bad_port_raises_clean_exit():
    with pytest.raises(SystemExit) as e:
        cli._url_to_conn("clickhouse://h:99999/db")
    assert e.value.code == 1  # QUERY_ERROR, not a raw ValueError traceback
