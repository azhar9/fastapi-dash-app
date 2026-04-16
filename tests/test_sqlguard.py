"""Unit tests for the SQL safety layer.

These don't touch the LLM or the DB — they exercise the pure function
that protects the /ask pipeline.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "api"))

from app.sqlguard import SqlSafetyError, sanitise  # noqa: E402


def test_accepts_simple_select():
    out = sanitise("SELECT 1")
    assert out.upper().startswith("SELECT 1")
    assert "LIMIT 1000" in out


def test_accepts_with_cte():
    out = sanitise("WITH x AS (SELECT 1) SELECT * FROM x")
    assert "LIMIT 1000" in out


def test_strips_trailing_semicolon():
    out = sanitise("SELECT * FROM prices;")
    assert ";" not in out


def test_preserves_existing_limit():
    out = sanitise("SELECT * FROM prices LIMIT 5")
    assert out.upper().count("LIMIT") == 1


@pytest.mark.parametrize(
    "bad_sql",
    [
        "",
        "DROP TABLE prices",
        "DELETE FROM holdings",
        "UPDATE portfolios SET name = 'x'",
        "INSERT INTO prices VALUES (1)",
        "ALTER TABLE prices ADD COLUMN x INT",
        "TRUNCATE prices",
        "GRANT ALL ON prices TO postgres",
        "CREATE TABLE evil (x INT)",
        "COPY prices TO '/tmp/x.csv'",
        "SELECT 1; DROP TABLE prices",
        "SELECT 1; SELECT 2",
        "SET ROLE postgres",
    ],
)
def test_rejects_dangerous(bad_sql):
    with pytest.raises(SqlSafetyError):
        sanitise(bad_sql)
