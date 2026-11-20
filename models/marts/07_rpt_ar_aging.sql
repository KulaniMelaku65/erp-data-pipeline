-- Receivables ageing for open invoices, as of the latest invoice date in the data.
-- {{days_overdue}} is filled in per database by pipeline/transform.py.
DROP TABLE IF EXISTS rpt_ar_aging;
CREATE TABLE rpt_ar_aging AS
SELECT
    i.invoice_no,
    i.customer_id,
    i.due_date,
    asof.as_of_date,
    i.total_incl_tax AS open_amount,
    {{days_overdue}} AS days_overdue,
    CASE
        WHEN {{days_overdue}} <= 0  THEN 'Not due'
        WHEN {{days_overdue}} <= 30 THEN '1-30'
        WHEN {{days_overdue}} <= 60 THEN '31-60'
        WHEN {{days_overdue}} <= 90 THEN '61-90'
        ELSE '90+'
    END AS aging_bucket
FROM stg_sales_invoices i
CROSS JOIN (SELECT MAX(invoice_date) AS as_of_date FROM stg_sales_invoices) asof
WHERE i.status = 'Open';
