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
