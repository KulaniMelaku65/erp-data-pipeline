from pipeline.quality import check_sql, run_checks
from pipeline.run import run
from pipeline.transform import render

import pytest


def test_end_to_end_builds_models_and_passes_checks(client, wh):
    summary = run(client, wh)
    assert summary.ok, summary.checks_failed
    assert summary.loaded["generalLedgerEntries"] > 1000
    assert {"fact_sales", "fact_gl", "dim_date", "rpt_monthly_pnl", "rpt_ar_aging"} <= set(summary.models)

    # Staging cleaned the messy master data
    names = [r[0] for r in wh.query("SELECT customer_name FROM dim_customer")]
    assert all(n == n.strip() for n in names)
    assert wh.query("SELECT COUNT(*) FROM dim_customer WHERE country_code <> UPPER(country_code)")[0][0] == 0

    # Profit report adds up to the ledger
    pnl = dict(wh.query("SELECT account_category, SUM(amount) FROM rpt_monthly_pnl GROUP BY account_category"))
    revenue = wh.query("SELECT SUM(credit) - SUM(debit) FROM fact_gl WHERE account_no = '4100'")[0][0]
    assert pnl["Income"] == pytest.approx(revenue, abs=0.05)


def test_second_run_is_incremental(client, wh, mock_bc):
    run(client, wh)
    item = mock_bc.data["items"][0]
    mock_bc.touch("items", item["id"], unitPrice=999.99)

    # No lookback here: the sample master data shares one timestamp, so a
    # 10-minute overlap would legitimately re-read every item.
    summary = run(client, wh, lookback_minutes=0)
    assert summary.loaded["items"] == 1          # only the edited item came back
    assert summary.loaded["generalLedgerEntries"] == 0
    assert wh.query("SELECT unit_price FROM dim_item WHERE item_id = ?", (item["id"],))[0][0] == 999.99
    assert wh.query("SELECT COUNT(*) FROM raw_items")[0][0] == 30


def test_unbalanced_document_fails_the_run(client, wh, mock_bc):
    entries = mock_bc.data["generalLedgerEntries"]
    mock_bc.add("generalLedgerEntries", dict(entries[0], id="broken-entry", entryNumber=999999, debitAmount=100.0, creditAmount=0.0))
    summary = run(client, wh)
    assert not summary.ok
    assert "gl_document_balances" in summary.checks_failed
    assert "trial_balance_zero" in summary.checks_failed


def test_full_refresh_reloads_everything(client, wh):
    run(client, wh)
    summary = run(client, wh, full_refresh=True)
    assert summary.loaded["customers"] == 40
    assert wh.query("SELECT COUNT(*) FROM raw_customers")[0][0] == 40


def test_check_sql_generation():
    assert "HAVING COUNT(*) > 1" in check_sql({"type": "unique", "table": "t", "column": "c", "name": "x"})
    assert "LEFT JOIN d r" in check_sql({"type": "relationship", "table": "t", "column": "c", "to_table": "d", "to_column": "k", "name": "x"})
    with pytest.raises(ValueError):
        check_sql({"type": "magic", "table": "t", "column": "c", "name": "x"})


def test_render_macros_per_dialect():
    assert "julianday" in render("SELECT {{days_overdue}}", "sqlite")
    assert "AS DATE" in render("SELECT {{days_overdue}}", "postgres")
    with pytest.raises(ValueError):
        render("SELECT {{nope}}", "sqlite")
