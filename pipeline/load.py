"""Land API records in typed ``raw_*`` tables, idempotently.

Each entity maps API fields to warehouse columns. Loads are upserts keyed on
the BC ``id`` (a GUID that never changes), so re-running a load, or loading an
overlapping window, never creates duplicates. A ``pipeline_state`` table holds
one watermark per entity: the latest ``lastModifiedDateTime`` loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .warehouse import Warehouse


@dataclass(frozen=True)
class Entity:
    api_name: str
    table: str
    columns: tuple[tuple[str, str, str], ...]  # (column, api field, logical type)


def _e(api_name: str, table: str, *columns: tuple[str, str, str]) -> Entity:
    base = (("id", "id", "text"),)
    tail = (("last_modified", "lastModifiedDateTime", "timestamp"),)
    return Entity(api_name, table, base + columns + tail)


ENTITIES: tuple[Entity, ...] = (
    _e("accounts", "raw_accounts",
       ("number", "number", "text"), ("display_name", "displayName", "text"), ("category", "category", "text")),
    _e("customers", "raw_customers",
       ("number", "number", "text"), ("display_name", "displayName", "text"), ("type", "type", "text"),
       ("city", "city", "text"), ("country", "country", "text"), ("email", "email", "text")),
    _e("vendors", "raw_vendors",
       ("number", "number", "text"), ("display_name", "displayName", "text"), ("country", "country", "text")),
    _e("items", "raw_items",
       ("number", "number", "text"), ("display_name", "displayName", "text"), ("type", "type", "text"),
       ("item_category_code", "itemCategoryCode", "text"), ("unit_cost", "unitCost", "decimal"),
       ("unit_price", "unitPrice", "decimal")),
    _e("salesInvoices", "raw_sales_invoices",
       ("number", "number", "text"), ("invoice_date", "invoiceDate", "text"), ("due_date", "dueDate", "text"),
       ("customer_id", "customerId", "text"), ("customer_number", "customerNumber", "text"),
       ("total_excl_tax", "totalAmountExcludingTax", "money"), ("total_tax", "totalTaxAmount", "money"),
       ("total_incl_tax", "totalAmountIncludingTax", "money"), ("status", "status", "text")),
    _e("salesInvoiceLines", "raw_sales_invoice_lines",
       ("document_id", "documentId", "text"), ("sequence", "sequence", "int"), ("item_id", "itemId", "text"),
       ("line_type", "lineType", "text"), ("description", "description", "text"),
       ("quantity", "quantity", "decimal"), ("unit_price", "unitPrice", "decimal"),
       ("discount_amount", "discountAmount", "money"), ("amount_excl_tax", "amountExcludingTax", "money"),
       ("tax_percent", "taxPercent", "decimal")),
    _e("generalLedgerEntries", "raw_gl_entries",
       ("entry_number", "entryNumber", "int"), ("posting_date", "postingDate", "text"),
       ("document_number", "documentNumber", "text"), ("document_type", "documentType", "text"),
       ("account_id", "accountId", "text"), ("account_number", "accountNumber", "text"),
       ("description", "description", "text"), ("debit_amount", "debitAmount", "money"),
       ("credit_amount", "creditAmount", "money")),
)

ENTITY_BY_API = {e.api_name: e for e in ENTITIES}


def ensure_schema(wh: Warehouse) -> None:
    for entity in ENTITIES:
        cols = ", ".join(
            f"{name} {wh.col_type(kind)}{' PRIMARY KEY' if name == 'id' else ''}" for name, _, kind in entity.columns
        )
        wh.execute(f"CREATE TABLE IF NOT EXISTS {entity.table} ({cols}, loaded_at {wh.col_type('timestamp')})")
    wh.execute(
        f"CREATE TABLE IF NOT EXISTS pipeline_state (entity TEXT PRIMARY KEY, watermark TEXT, "
        f"last_run_at {wh.col_type('timestamp')}, rows_loaded {wh.col_type('int')})"
    )
    wh.commit()


def upsert(wh: Warehouse, entity: Entity, records: Iterable[dict], batch_size: int = 500) -> tuple[int, str | None]:
    """Upsert records; return (rows written, max lastModifiedDateTime seen)."""
    names = [name for name, _, _ in entity.columns] + ["loaded_at"]
    marks = ", ".join([wh.placeholder] * len(names))
    updates = ", ".join(f"{n} = excluded.{n}" for n in names if n != "id")
    sql = f"INSERT INTO {entity.table} ({', '.join(names)}) VALUES ({marks}) ON CONFLICT (id) DO UPDATE SET {updates}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total, newest, batch = 0, None, []
    for record in records:
        missing = [field for _, field, _ in entity.columns if field not in record]
        if missing:
            raise ValueError(f"{entity.api_name} record {record.get('id')} is missing {missing}")
        batch.append([record[field] for _, field, _ in entity.columns] + [now])
        stamp = record["lastModifiedDateTime"]
        newest = stamp if newest is None or stamp > newest else newest
        if len(batch) >= batch_size:
            wh.executemany(sql, batch)
            total += len(batch)
            batch = []
    if batch:
        wh.executemany(sql, batch)
        total += len(batch)
    return total, newest


def get_watermark(wh: Warehouse, entity: Entity) -> str | None:
    rows = wh.query(f"SELECT watermark FROM pipeline_state WHERE entity = {wh.placeholder}", (entity.api_name,))
    return rows[0][0] if rows else None


def set_watermark(wh: Warehouse, entity: Entity, watermark: str | None, rows_loaded: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = wh.placeholder
    wh.execute(
        f"INSERT INTO pipeline_state (entity, watermark, last_run_at, rows_loaded) VALUES ({p}, {p}, {p}, {p}) "
        "ON CONFLICT (entity) DO UPDATE SET watermark = COALESCE(excluded.watermark, pipeline_state.watermark), "
        "last_run_at = excluded.last_run_at, rows_loaded = excluded.rows_loaded",
        (entity.api_name, watermark, now, rows_loaded),
    )


def lookback(watermark: str | None, minutes: int) -> str | None:
    """Step the watermark back a little so records saved in the same second are not missed.

    Upserts make the overlap harmless: a record read twice is written once.
    """
    if not watermark:
        return None
    moment = datetime.strptime(watermark, "%Y-%m-%dT%H:%M:%SZ") - timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
