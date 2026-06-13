from chsql.client import _resolve


def test_auto_defaults_to_native():
    proto, c = _resolve({"host": "h"})
    assert proto == "native" and c["port"] == 9000


def test_auto_native_secure_port():
    proto, c = _resolve({"secure": True})
    assert proto == "native" and c["port"] == 9440


def test_auto_picks_http_by_port():
    for port in (443, 8123, 8443):
        proto, c = _resolve({"port": port})
        assert proto == "http" and c["port"] == port


def test_explicit_http_default_ports():
    proto, c = _resolve({"protocol": "http"})
    assert proto == "http" and c["port"] == 8123
    _, c_secure = _resolve({"protocol": "http", "secure": True})
    assert c_secure["port"] == 8443


def test_explicit_native_overrides_http_port():
    proto, c = _resolve({"protocol": "native", "port": 443})
    assert proto == "native" and c["port"] == 443
