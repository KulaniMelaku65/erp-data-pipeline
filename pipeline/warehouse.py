"""Warehouse connections for PostgreSQL (production) and SQLite (local runs and tests).

Both speak the same SQL for everything the pipeline does: typed raw tables,
``INSERT ... ON CONFLICT DO UPDATE`` upserts, and ``CREATE TABLE AS`` models.
Only the column types and the parameter placeholder differ.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterable, Iterator, Sequence

TYPE_MAP = {
    "sqlite": {"text": "TEXT", "int": "INTEGER", "money": "REAL", "decimal": "REAL", "timestamp": "TEXT"},
    "postgres": {"text": "TEXT", "int": "BIGINT", "money": "NUMERIC(18,2)", "decimal": "NUMERIC(18,4)", "timestamp": "TIMESTAMPTZ"},
}


class Warehouse:
    dialect: str
    placeholder: str

    def execute(self, sql: str, params: Sequence | None = None) -> None: ...
    def executemany(self, sql: str, rows: Iterable[Sequence]) -> None: ...
    def query(self, sql: str, params: Sequence | None = None) -> list[tuple]: ...
    def script(self, sql: str) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

    @contextmanager
    def transaction(self) -> Iterator["Warehouse"]:
        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise

    def col_type(self, logical: str) -> str:
        return TYPE_MAP[self.dialect][logical]


class SQLiteWarehouse(Warehouse):
    dialect = "sqlite"
    placeholder = "?"

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)

    def execute(self, sql, params=None):
        self.conn.execute(sql, params or ())

    def executemany(self, sql, rows):
        self.conn.executemany(sql, rows)

    def query(self, sql, params=None):
        return self.conn.execute(sql, params or ()).fetchall()

    def script(self, sql):
        self.conn.executescript(sql)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


class PostgresWarehouse(Warehouse):
    dialect = "postgres"
    placeholder = "%s"

    def __init__(self, dsn: str):
        import psycopg  # imported lazily so SQLite runs need no driver

        self.conn = psycopg.connect(dsn)

    def execute(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def executemany(self, sql, rows):
        with self.conn.cursor() as cur:
            cur.executemany(sql, list(rows))

    def query(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def script(self, sql):
        with self.conn.cursor() as cur:
            for statement in split_statements(sql):
                cur.execute(statement)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def split_statements(sql: str) -> list[str]:
    """Split a model file on semicolons, ignoring ``--`` comment lines."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def connect(url: str) -> Warehouse:
    """``sqlite:///path.db``, ``sqlite://`` (in memory) or ``postgresql://user:pass@host/db``."""
    if url.startswith("sqlite://"):
        path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else ":memory:"
        return SQLiteWarehouse(path or ":memory:")
    if url.startswith(("postgres://", "postgresql://")):
        return PostgresWarehouse(url)
    raise ValueError(f"Unsupported warehouse URL: {url}")
