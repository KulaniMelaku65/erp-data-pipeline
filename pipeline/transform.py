"""Build the warehouse models: staging tables, then marts.

Models are plain SQL files under ``models/``, run in folder then file-name
order (``staging/01_...`` before ``marts/01_...``). Each file drops and rebuilds
its table, so a transform run is repeatable. The few expressions that differ
between SQLite and PostgreSQL are written as ``{{macro}}`` and filled in here.
``dim_date`` is generated in Python because calendar generation is the one
thing the two databases do very differently.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from .warehouse import Warehouse, split_statements

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
LAYERS = ("staging", "marts")

MACROS = {
    "sqlite": {"days_overdue": "CAST(julianday(asof.as_of_date) - julianday(i.due_date) AS INTEGER)"},
    "postgres": {"days_overdue": "(CAST(asof.as_of_date AS DATE) - CAST(i.due_date AS DATE))"},
}


def render(sql: str, dialect: str) -> str:
    for name, expression in MACROS[dialect].items():
        sql = sql.replace("{{" + name + "}}", expression)
    if "{{" in sql:
        raise ValueError(f"Unknown macro in model: {sql[sql.index('{{'):][:40]}")
    return sql


def model_files(models_dir: Path = MODELS_DIR, layer: str | None = None) -> list[Path]:
    layers = (layer,) if layer else LAYERS
    return [path for name in layers for path in sorted((models_dir / name).glob("*.sql"))]


def build_dim_date(wh: Warehouse) -> int:
    rows = wh.query(
        "SELECT MIN(d), MAX(d) FROM ("
        "SELECT posting_date AS d FROM stg_gl_entries UNION ALL "
        "SELECT invoice_date FROM stg_sales_invoices UNION ALL "
        "SELECT due_date FROM stg_sales_invoices) x"
    )
    first, last = rows[0]
    wh.execute("DROP TABLE IF EXISTS dim_date")
    wh.execute(
        "CREATE TABLE dim_date (date_key INTEGER PRIMARY KEY, calendar_date TEXT, year INTEGER, "
        "quarter INTEGER, month INTEGER, month_name TEXT, year_month TEXT, day_of_week TEXT, is_weekend INTEGER)"
    )
    if not first:
        return 0
    start, end = date.fromisoformat(first).replace(month=1, day=1), date.fromisoformat(last).replace(month=12, day=31)
    days, day = [], start
    while day <= end:
        days.append(
            (int(day.strftime("%Y%m%d")), day.isoformat(), day.year, (day.month - 1) // 3 + 1, day.month,
             day.strftime("%B"), day.strftime("%Y-%m"), day.strftime("%A"), int(day.weekday() >= 5))
        )
        day += timedelta(days=1)
    marks = ", ".join([wh.placeholder] * 9)
    wh.executemany(f"INSERT INTO dim_date VALUES ({marks})", days)
    return len(days)


def run_models(wh: Warehouse, models_dir: Path = MODELS_DIR) -> list[str]:
    """Rebuild every model. On PostgreSQL this is one transaction: all models change, or none do."""
    built = []
    with wh.transaction():
        for layer in LAYERS:
            for path in model_files(models_dir, layer):
                for statement in split_statements(render(path.read_text(), wh.dialect)):
                    wh.execute(statement)
                built.append(path.stem.split("_", 1)[1])
            if layer == "staging":
                log.info("dim_date: %s days", build_dim_date(wh))
                built.append("dim_date")
    log.info("Built %s models", len(built))
    return built
