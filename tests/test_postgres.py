"""Runs the full pipeline against a real PostgreSQL when TEST_POSTGRES_URL is set (CI does)."""

import os

import pytest

from pipeline.run import run
from pipeline.warehouse import connect

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL not set")


def test_pipeline_on_postgres(client):
    wh = connect(URL)
    try:
        for table in [r[0] for r in wh.query("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]:
            wh.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        wh.commit()

        summary = run(client, wh)
        assert summary.ok, summary.checks_failed
        assert wh.query("SELECT COUNT(*) FROM fact_gl")[0][0] == summary.loaded["generalLedgerEntries"]

        again = run(client, wh, lookback_minutes=0)
        assert again.loaded["generalLedgerEntries"] == 0
    finally:
        wh.close()
