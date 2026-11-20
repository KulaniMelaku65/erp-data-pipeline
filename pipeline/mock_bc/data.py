"""Deterministic sample data shaped like the Business Central API v2.0.

Nothing here comes from a real company. The generator builds a small trading
business: customers, vendors, items, a chart of accounts, posted sales
invoices with lines, and the general ledger entries those invoices post.
Every invoice posts a balanced set of G/L entries (receivable = revenue + VAT,
plus cost of goods sold against inventory), so the warehouse checks have
something real to verify.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone

VAT_RATE = 0.15

ACCOUNTS = [
    # number, name, category
    ("1100", "Cash and Bank", "Assets"),
    ("1200", "Accounts Receivable", "Assets"),
    ("1300", "Inventory", "Assets"),
    ("2100", "Accounts Payable", "Liabilities"),
    ("2200", "VAT Payable", "Liabilities"),
    ("3100", "Share Capital", "Equity"),
    ("4100", "Sales Revenue", "Income"),
    ("5100", "Cost of Goods Sold", "CostOfGoodsSold"),
    ("6100", "Salaries", "Expense"),
    ("6200", "Rent", "Expense"),
    ("6300", "Utilities", "Expense"),
]

CITIES = [
    ("Addis Ababa", "ET"), ("Nairobi", "KE"), ("Kampala", "UG"),
    ("Kigali", "RW"), ("Dar es Salaam", "TZ"), ("Djibouti", "DJ"),
]

ITEM_CATEGORIES = ["FEED", "PACKAGING", "EQUIPMENT", "SPARES"]


def _uid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128)))


def _ts(d: date, rng: random.Random) -> str:
    moment = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(
        hours=rng.randint(8, 18), minutes=rng.randint(0, 59)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(seed: int = 42, start: date = date(2026, 1, 1), months: int = 10) -> dict[str, list[dict]]:
    """Return every entity set keyed by its API name."""
    rng = random.Random(seed)
    created = _ts(start - timedelta(days=30), rng)

    accounts = [
        {
            "id": _uid(rng),
            "number": number,
            "displayName": name,
            "category": category,
            "lastModifiedDateTime": created,
        }
        for number, name, category in ACCOUNTS
    ]
    acc = {a["number"]: a for a in accounts}

    customers = []
    for i in range(1, 41):
        city, country = rng.choice(CITIES)
        name = f"Customer {i:03d} Trading"
        customers.append(
            {
                "id": _uid(rng),
                "number": f"C{i:05d}",
                # Some names carry stray spaces and emails odd casing, as real
                # master data does; the staging models clean them.
                "displayName": f"  {name} " if i % 7 == 0 else name,
                "type": "Company",
                "city": city,
                "country": country.lower() if i % 9 == 0 else country,
                "email": f"Accounts{i}@Customer{i:03d}.example" if i % 5 == 0 else f"accounts{i}@customer{i:03d}.example",
                "lastModifiedDateTime": created,
            }
        )

    vendors = [
        {
            "id": _uid(rng),
            "number": f"V{i:05d}",
            "displayName": f"Supplier {i:02d} PLC",
            "country": rng.choice(CITIES)[1],
            "lastModifiedDateTime": created,
        }
        for i in range(1, 16)
    ]

    items = []
    for i in range(1, 31):
        cost = round(rng.uniform(5, 400), 2)
        items.append(
            {
                "id": _uid(rng),
                "number": f"ITEM-{i:04d}",
                "displayName": f"{rng.choice(ITEM_CATEGORIES).title()} product {i}",
                "type": "Inventory",
                "itemCategoryCode": rng.choice(ITEM_CATEGORIES),
                "unitCost": cost,
                "unitPrice": round(cost * rng.uniform(1.15, 1.6), 2),
                "lastModifiedDateTime": created,
            }
        )

    invoices, lines, gl = [], [], []
    entry_no = 0

    def post(posting_date: date, doc_no: str, doc_type: str, account: str, debit: float, credit: float, desc: str) -> None:
        nonlocal entry_no
        entry_no += 1
        gl.append(
            {
                "id": _uid(rng),
                "entryNumber": entry_no,
                "postingDate": posting_date.isoformat(),
                "documentNumber": doc_no,
                "documentType": doc_type,
                "accountId": acc[account]["id"],
                "accountNumber": account,
                "description": desc,
                "debitAmount": round(debit, 2),
                "creditAmount": round(credit, 2),
                "lastModifiedDateTime": _ts(posting_date, rng),
            }
        )

    inv_no = 100000
    day = start
    end = date(start.year + (start.month - 1 + months) // 12, (start.month - 1 + months) % 12 + 1, 1)
    while day < end:
        # 0-3 invoices per working day
        if day.weekday() < 5:
            for _ in range(rng.randint(0, 3)):
                inv_no += 1
                customer = rng.choice(customers)
                inv_id = _uid(rng)
                net_total = cost_total = 0.0
                for seq in range(1, rng.randint(1, 4) + 1):
                    item = rng.choice(items)
                    qty = rng.randint(1, 25)
                    discount = round(item["unitPrice"] * qty * rng.choice([0, 0, 0, 0.05, 0.1]), 2)
                    net = round(item["unitPrice"] * qty - discount, 2)
                    net_total += net
                    cost_total += round(item["unitCost"] * qty, 2)
                    lines.append(
                        {
                            "id": _uid(rng),
                            "documentId": inv_id,
                            "sequence": seq * 10000,
                            "itemId": item["id"],
                            "lineType": "Item",
                            "description": item["displayName"],
                            "quantity": qty,
                            "unitPrice": item["unitPrice"],
                            "discountAmount": discount,
                            "amountExcludingTax": net,
                            "taxPercent": VAT_RATE * 100,
                            "lastModifiedDateTime": _ts(day, rng),
                        }
                    )
                net_total = round(net_total, 2)
                vat = round(net_total * VAT_RATE, 2)
                doc = f"PSI{inv_no}"
                invoices.append(
                    {
                        "id": inv_id,
                        "number": doc,
                        "invoiceDate": day.isoformat(),
                        "dueDate": (day + timedelta(days=30)).isoformat(),
                        "customerId": customer["id"],
                        "customerNumber": customer["number"],
                        "totalAmountExcludingTax": net_total,
                        "totalTaxAmount": vat,
                        "totalAmountIncludingTax": round(net_total + vat, 2),
                        "status": "Open" if day > end - timedelta(days=45) else rng.choice(["Paid", "Paid", "Open"]),
                        "lastModifiedDateTime": _ts(day, rng),
                    }
                )
                post(day, doc, "Invoice", "1200", net_total + vat, 0, f"Invoice {doc}")
                post(day, doc, "Invoice", "4100", 0, net_total, f"Invoice {doc}")
                post(day, doc, "Invoice", "2200", 0, vat, f"Invoice {doc}")
                post(day, doc, "Invoice", "5100", cost_total, 0, f"COGS {doc}")
                post(day, doc, "Invoice", "1300", 0, cost_total, f"COGS {doc}")
        # Month-end expenses paid from the bank
        if (day + timedelta(days=1)).day == 1:
            for account, low, high in (("6100", 18000, 22000), ("6200", 4000, 4000), ("6300", 600, 1100)):
                amount = round(rng.uniform(low, high), 2)
                doc = f"GJ{day:%Y%m}-{account}"
                post(day, doc, "Payment", account, amount, 0, f"{acc[account]['displayName']} {day:%b %Y}")
                post(day, doc, "Payment", "1100", 0, amount, f"{acc[account]['displayName']} {day:%b %Y}")
        day += timedelta(days=1)

    return {
        "accounts": accounts,
        "customers": customers,
        "vendors": vendors,
        "items": items,
        "salesInvoices": invoices,
        "salesInvoiceLines": lines,
        "generalLedgerEntries": gl,
    }
