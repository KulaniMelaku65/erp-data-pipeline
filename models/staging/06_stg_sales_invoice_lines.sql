-- Item lines only; comment and G/L-account lines are not sales of goods.
DROP TABLE IF EXISTS stg_sales_invoice_lines;
CREATE TABLE stg_sales_invoice_lines AS
SELECT
    id               AS line_id,
    document_id      AS invoice_id,
    sequence         AS line_no,
    item_id,
    description,
    quantity,
    unit_price,
    discount_amount,
    amount_excl_tax  AS net_amount,
    tax_percent
FROM raw_sales_invoice_lines
WHERE line_type = 'Item';
