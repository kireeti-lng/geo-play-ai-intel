-- Question: Show ARPDAU by country for the last 7 days in the month of may?
-- Generated: 20260820_121018 by openai/gpt-5.2

WITH may_window AS (
  SELECT
    MAX(event_date) AS may_end_date
  FROM fact_user_daily
  WHERE EXTRACT(MONTH FROM event_date) = 5
    AND event_date <= CURRENT_DATE()
),
date_bounds AS (
  SELECT
    may_end_date,
    GREATEST(DATE_TRUNC(may_end_date, MONTH), DATE_SUB(may_end_date, INTERVAL 6 DAY)) AS may_start_date
  FROM may_window
),
daily_country AS (
  SELECT
    fud.event_date,
    fud.country,
    SUM(IFNULL(fud.revenue_iap_usd, 0) + IFNULL(fud.ad_revenue_usd, 0)) AS total_revenue_usd,
    COUNT(DISTINCT IF(fud.has_session, fud.user_id, NULL)) AS dau
  FROM fact_user_daily AS fud
  CROSS JOIN date_bounds AS b
  WHERE fud.event_date BETWEEN b.may_start_date AND b.may_end_date
    AND EXTRACT(MONTH FROM fud.event_date) = 5
  GROUP BY 1, 2
)
SELECT
  event_date,
  country,
  SAFE_DIVIDE(total_revenue_usd, dau) AS arpdau_usd
FROM daily_country
ORDER BY event_date, country;
