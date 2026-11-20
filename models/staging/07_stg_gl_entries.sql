DROP TABLE IF EXISTS stg_gl_entries;
CREATE TABLE stg_gl_entries AS
SELECT
    entry_number     AS entry_no,
    posting_date,
    document_number  AS document_no,
    document_type,
    account_number   AS account_no,
    description,
    debit_amount     AS debit,
    credit_amount    AS credit
FROM raw_gl_entries;
