"""Lightweight SQL safety checks layered on top of the read-only PG role.

The RO role is the hard guarantee — Postgres refuses anything outside
SELECT/USAGE grants. These checks are the *early* line of defence: we
reject obviously unsafe input before opening a connection, so the audit
log doesn't fill with Postgres permission errors and the caller gets a
clear 400 back instead of a 500.
"""
from __future__ import annotations

import re

_BANNED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|"
    r"COPY|CALL|MERGE|ATTACH|DETACH|VACUUM|ANALYZE|REINDEX|CLUSTER|"
    r"LISTEN|NOTIFY|LOCK|COMMENT|SECURITY|SET\s+ROLE|RESET\s+ROLE)\b",
    re.IGNORECASE,
)


class SqlSafetyError(ValueError):
    """Raised when the LLM-generated SQL fails structural validation."""


def sanitise(sql: str, row_cap: int = 1000) -> str:
    """Normalise and validate a SELECT-only SQL statement.

    Returns the cleaned SQL (with a LIMIT appended if missing).
    Raises SqlSafetyError on anything suspicious.
    """
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise SqlSafetyError("empty SQL")

    # Must be a read path.
    first_word = cleaned.split(None, 1)[0].upper()
    if first_word not in {"SELECT", "WITH"}:
        raise SqlSafetyError(f"only SELECT/WITH queries are allowed, got: {first_word}")

    # No statement stacking. asyncpg's .fetch only runs one statement,
    # but rejecting here gives a cleaner error and blocks tricks like
    # embedded "--; DELETE" comments.
    if ";" in cleaned:
        raise SqlSafetyError("multiple statements are not allowed")

    if _BANNED.search(cleaned):
        raise SqlSafetyError("DML / DDL keywords are not allowed")

    # Append a LIMIT if the LLM forgot one. We don't try to parse an
    # existing LIMIT precisely — if the query already has 'limit', trust it.
    if re.search(r"\blimit\s+\d+", cleaned, re.IGNORECASE) is None:
        cleaned = f"{cleaned} LIMIT {row_cap}"

    return cleaned
