from chsql.client import classify


def test_reads():
    for sql in [
        "SELECT 1",
        "  select * from t",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SHOW TABLES",
        "DESCRIBE TABLE t",
        "EXPLAIN SELECT 1",
        "-- a comment\nSELECT 1",
        "/* block */ SELECT 1",
    ]:
        assert classify(sql) == "read", sql


def test_writes():
    for sql in ["INSERT INTO t VALUES (1)", "alter table t delete where 1",
                "OPTIMIZE TABLE t", "SYSTEM RELOAD"]:
        assert classify(sql) == "write", sql


def test_ddl():
    for sql in ["CREATE TABLE t (a Int)", "DROP TABLE t", "truncate table t",
                "RENAME TABLE a TO b"]:
        assert classify(sql) == "ddl", sql


def test_multi_statement_takes_highest_privilege():
    # A trailing statement must not sneak past a leading SELECT.
    assert classify("SELECT 1; DROP TABLE x") == "ddl"
    assert classify("SELECT 1; INSERT INTO t VALUES (1)") == "write"
    assert classify("SELECT 1; SELECT 2") == "read"
    assert classify("SELECT 1;") == "read"


def test_row_cap_settings():
    from chsql.client import row_cap_settings
    assert row_cap_settings(0) is None
    assert row_cap_settings(-5) is None
    s = row_cap_settings(100)
    assert s == {"max_result_rows": 100, "result_overflow_mode": "break"}
