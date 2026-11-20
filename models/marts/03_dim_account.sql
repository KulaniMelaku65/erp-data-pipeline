-- statement tells reports which side of the books an account sits on.
DROP TABLE IF EXISTS dim_account;
CREATE TABLE dim_account AS
SELECT
    account_no,
    account_name,
    account_category,
    CASE WHEN account_category IN ('Income', 'CostOfGoodsSold', 'Expense') THEN 'Income Statement'
         ELSE 'Balance Sheet' END AS statement
FROM stg_accounts;
