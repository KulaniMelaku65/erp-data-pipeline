-- Monthly profit and loss by category. Income is shown positive, costs positive,
-- so profit = Income - CostOfGoodsSold - Expense.
DROP TABLE IF EXISTS rpt_monthly_pnl;
CREATE TABLE rpt_monthly_pnl AS
SELECT
    SUBSTR(posting_date, 1, 7) AS year_month,
    account_category,
    ROUND(CAST(SUM(CASE WHEN account_category = 'Income' THEN credit - debit
                        ELSE debit - credit END) AS NUMERIC), 2) AS amount
FROM fact_gl
WHERE account_category IN ('Income', 'CostOfGoodsSold', 'Expense')
GROUP BY SUBSTR(posting_date, 1, 7), account_category;
