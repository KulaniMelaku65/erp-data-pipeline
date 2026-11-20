-- One row per invoice line. Cost uses the item's current unit cost (a simplification:
-- production would use the Value Entry table for the exact cost posted).
DROP TABLE IF EXISTS fact_sales;
CREATE TABLE fact_sales AS
SELECT
    l.line_id,
    i.invoice_no,
    CAST(REPLACE(i.invoice_date, '-', '') AS INTEGER)                    AS date_key,
    i.invoice_date,
    i.customer_id,
    l.item_id,
    l.quantity,
    l.unit_price,
    l.discount_amount,
    l.net_amount,
    ROUND(CAST(l.quantity * it.unit_cost AS NUMERIC), 2)                AS cost_amount,
    ROUND(CAST(l.net_amount - l.quantity * it.unit_cost AS NUMERIC), 2) AS gross_margin,
    i.status                                                            AS invoice_status
FROM stg_sales_invoice_lines l
JOIN stg_sales_invoices i ON i.invoice_id = l.invoice_id
LEFT JOIN stg_items it    ON it.item_id = l.item_id;
