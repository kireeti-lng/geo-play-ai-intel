-- Question: What is the D7 retention by country for installs in the last 30 days?
-- Generated: 20260820_113100 by openai/gpt-5.6-luna

WITH eligible_installs AS (
  SELECT
    user_id,
    game_id,
    install_date,
    COALESCE(primary_country, 'Unknown') AS country
  FROM dim_user
  WHERE is_current = TRUE
    AND install_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                          AND DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
),
retention_by_country AS (
  SELECT
    i.country,
    COUNT(DISTINCT i.user_id) AS install_cohort_size,
    COUNT(DISTINCT IF(s.user_id IS NOT NULL, i.user_id, NULL)) AS d7_retained_users
  FROM eligible_installs AS i
  LEFT JOIN fact_sessions AS s
    ON s.user_id = i.user_id
   AND s.game_id = i.game_id
   AND s.event_date = DATE_ADD(i.install_date, INTERVAL 7 DAY)
  GROUP BY i.country
)
SELECT
  country,
  install_cohort_size,
  d7_retained_users,
  SAFE_DIVIDE(d7_retained_users, install_cohort_size) AS d7_retention
FROM retention_by_country
ORDER BY country;
