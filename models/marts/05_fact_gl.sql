DROP TABLE IF EXISTS fact_gl;
CREATE TABLE fact_gl AS
SELECT
    g.entry_no,
    CAST(REPLACE(g.posting_date, '-', '') AS INTEGER) AS date_key,
    g.posting_date,
    g.document_no,
    g.document_type,
    g.account_no,
    a.account_category,
    g.debit,
    g.credit,
    g.debit - g.credit                                AS net_amount
FROM stg_gl_entries g
LEFT JOIN dim_account a ON a.account_no = g.account_no;
