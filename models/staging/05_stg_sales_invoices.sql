-- Posted sales invoice headers.
DROP TABLE IF EXISTS stg_sales_invoices;
CREATE TABLE stg_sales_invoices AS
SELECT
    id               AS invoice_id,
    number           AS invoice_no,
    invoice_date,
    due_date,
    customer_id,
    total_excl_tax,
    total_tax,
    total_incl_tax,
    status
FROM raw_sales_invoices;
