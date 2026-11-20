"""Run the pipeline: extract -> load -> transform -> check.

Configuration comes from environment variables (see ``.env.example``):

    WAREHOUSE_URL      sqlite:///warehouse.db  or  postgresql://user:pass@host:5432/erp
    BC_BASE_URL        https://api.businesscentral.dynamics.com/v2.0/<tenant>/<environment>
    BC_COMPANY_NAME    optional; first company if empty
    BC_TOKEN_URL       https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
    BC_CLIENT_ID / BC_CLIENT_SECRET
    LOOKBACK_MINUTES   overlap on incremental loads (default 10)

Examples:

    python -m pipeline.run                 # incremental run
    python -m pipeline.run --full-refresh  # ignore watermarks, reload everything
    python -m pipeline.run --mock          # start the mock BC API in-process and run against it
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field

from .extract import BCConfig, BusinessCentralClient
from .load import ENTITIES, ensure_schema, get_watermark, lookback, set_watermark, upsert
from .quality import has_errors, run_checks
from .transform import run_models
from .warehouse import Warehouse, connect

log = logging.getLogger("pipeline")


@dataclass
class RunSummary:
    loaded: dict[str, int] = field(default_factory=dict)
    models: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    checks_warned: list[str] = field(default_factory=list)
    seconds: float = 0.0
    ok: bool = True


def config_from_env(env=os.environ) -> BCConfig:
    return BCConfig(
        base_url=env["BC_BASE_URL"].rstrip("/"),
        company_name=env.get("BC_COMPANY_NAME") or None,
        token_url=env.get("BC_TOKEN_URL"),
        client_id=env.get("BC_CLIENT_ID"),
        client_secret=env.get("BC_CLIENT_SECRET"),
    )


def extract_and_load(client: BusinessCentralClient, wh: Warehouse, full_refresh: bool, lookback_minutes: int) -> dict[str, int]:
    ensure_schema(wh)
    loaded = {}
    for entity in ENTITIES:
        since = None if full_refresh else lookback(get_watermark(wh, entity), lookback_minutes)
        with wh.transaction():
            rows, newest = upsert(wh, entity, client.fetch(entity.api_name, since))
            set_watermark(wh, entity, newest, rows)
        loaded[entity.api_name] = rows
        log.info("%-22s %6s rows%s", entity.api_name, rows, f" (since {since})" if since else "")
    return loaded


def run(client: BusinessCentralClient, wh: Warehouse, full_refresh: bool = False, lookback_minutes: int = 10) -> RunSummary:
    started = time.monotonic()
    summary = RunSummary()
    summary.loaded = extract_and_load(client, wh, full_refresh, lookback_minutes)
    summary.models = run_models(wh)
    results = run_checks(wh)
    summary.checks_failed = [r.name for r in results if not r.passed and r.severity == "error"]
    summary.checks_warned = [r.name for r in results if not r.passed and r.severity == "warn"]
    summary.ok = not has_errors(results)
    summary.seconds = round(time.monotonic() - started, 2)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Business Central -> warehouse pipeline")
    parser.add_argument("--full-refresh", action="store_true", help="Ignore watermarks and reload everything")
    parser.add_argument("--mock", action="store_true", help="Run against an in-process mock BC API")
    parser.add_argument("--warehouse", default=os.environ.get("WAREHOUSE_URL", "sqlite:///warehouse.db"))
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")

    mock = None
    if args.mock:
        from .mock_bc.server import MockBusinessCentral

        mock = MockBusinessCentral()
        base = mock.start()
        config = BCConfig(base_url=base, token_url=f"{base}/oauth2/token", client_id="demo", client_secret="demo")
    else:
        config = config_from_env()

    wh = connect(args.warehouse)
    try:
        summary = run(
            BusinessCentralClient(config), wh,
            full_refresh=args.full_refresh,
            lookback_minutes=int(os.environ.get("LOOKBACK_MINUTES", 10)),
        )
    finally:
        wh.close()
        if mock:
            mock.stop()

    print(json.dumps(asdict(summary), indent=2))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
