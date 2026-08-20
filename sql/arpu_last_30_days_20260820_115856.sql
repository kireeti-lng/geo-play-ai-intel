-- Question: What is ARPU for the last 30 days?
-- Generated: 20260820_115856 by openai/gpt-5.2

WITH date_window AS (
  SELECT
    DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AS start_date,
    DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY) AS end_date
),
base AS (
  SELECT
    ud.user_id,
    ud.event_date,
    ud.has_session,
    COALESCE(ud.revenue_iap_usd, 0) + COALESCE(ud.ad_revenue_usd, 0) AS total_revenue_usd
  FROM fact_user_daily ud
  CROSS JOIN date_window w
  WHERE ud.event_date BETWEEN w.start_date AND w.end_date
),
agg AS (
  SELECT
    SUM(total_revenue_usd) AS total_revenue_usd,
    COUNT(DISTINCT IF(has_session, user_id, NULL)) AS active_users
  FROM base
)
SELECT
  w.start_date,
  w.end_date,
  a.total_revenue_usd,
  a.active_users,
  SAFE_DIVIDE(a.total_revenue_usd, a.active_users) AS arpu_usd
FROM agg a
CROSS JOIN date_window w;
