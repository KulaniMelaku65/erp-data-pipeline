"""Data-quality checks defined in ``checks.yml``.

Every check is a query that returns the *failing* rows; zero rows means pass.
Generic checks (unique, not_null, relationship) are turned into SQL here; the
accounting rules are written as SQL directly in the YAML file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from .warehouse import Warehouse

log = logging.getLogger(__name__)

CHECKS_FILE = Path(__file__).resolve().parent.parent / "checks.yml"


@dataclass
class CheckResult:
    name: str
    severity: str
    failures: int
    sample: list[tuple]

    @property
    def passed(self) -> bool:
        return self.failures == 0


def check_sql(check: dict) -> str:
    kind = check["type"]
    if kind == "sql":
        return check["sql"]
    table, column = check["table"], check["column"]
    if kind == "unique":
        return f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column} HAVING COUNT(*) > 1"
    if kind == "not_null":
        return f"SELECT * FROM {table} WHERE {column} IS NULL"
    if kind == "relationship":
        return (
            f"SELECT t.{column} FROM {table} t LEFT JOIN {check['to_table']} r "
            f"ON r.{check['to_column']} = t.{column} WHERE t.{column} IS NOT NULL AND r.{check['to_column']} IS NULL"
        )
    raise ValueError(f"Unknown check type {kind!r} in {check['name']}")


def load_checks(path: Path = CHECKS_FILE) -> list[dict]:
    checks = yaml.safe_load(path.read_text())["checks"]
    names = [c["name"] for c in checks]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate check names in checks.yml")
    return checks


def run_checks(wh: Warehouse, path: Path = CHECKS_FILE) -> list[CheckResult]:
    results = []
    for check in load_checks(path):
        rows = wh.query(check_sql(check))
        result = CheckResult(check["name"], check.get("severity", "error"), len(rows), rows[:5])
        level = logging.INFO if result.passed else (logging.ERROR if result.severity == "error" else logging.WARNING)
        log.log(level, "%-40s %s", check["name"], "pass" if result.passed else f"FAIL ({result.failures} rows)")
        results.append(result)
    return results


def has_errors(results: list[CheckResult]) -> bool:
    return any(not r.passed and r.severity == "error" for r in results)
