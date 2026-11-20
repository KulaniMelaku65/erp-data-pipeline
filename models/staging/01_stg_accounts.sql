-- Chart of accounts, one row per G/L account.
DROP TABLE IF EXISTS stg_accounts;
CREATE TABLE stg_accounts AS
SELECT
    id                  AS account_id,
    number              AS account_no,
    TRIM(display_name)  AS account_name,
    category            AS account_category
FROM raw_accounts;
