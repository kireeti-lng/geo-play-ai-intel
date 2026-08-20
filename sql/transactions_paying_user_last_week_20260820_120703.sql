-- Question: What is the Transactions / Paying User last week?
-- Generated: 20260820_120703 by openai/gpt-5.2

WITH week_bounds AS (
  SELECT
    DATE_SUB(d.week_start_monday, INTERVAL 7 DAY) AS week_start,
    DATE_SUB(d.week_start_monday, INTERVAL 1 DAY) AS week_end
  FROM dim_date d
  WHERE d.full_date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
),
base AS (
  SELECT
    wb.week_start,
    wb.week_end,
    COUNTIF(p.is_successful_purchase) AS transactions,
    COUNT(DISTINCT IF(p.is_successful_purchase, p.user_id, NULL)) AS paying_users
  FROM week_bounds wb
  JOIN fact_purchases p
    ON p.event_date BETWEEN wb.week_start AND wb.week_end
  GROUP BY 1, 2
)
SELECT
  week_start,
  week_end,
  transactions,
  paying_users,
  SAFE_DIVIDE(transactions, paying_users) AS transactions_per_paying_user
FROM base;
