-- Question: What is the D7 retention by country for installs in the last 30 days?
-- Generated: 20260820_205923 by the NL-to-SQL agent

SELECT
  m.org_id,
  m.game_id,
  m.game_client_id,
  m.country,
  SAFE_DIVIDE(SUM(COALESCE(m.numerator, 0)), SUM(COALESCE(m.denominator, 0))) AS d7_retention,
  MIN(m.obs_date) AS first_date,
  MAX(m.obs_date) AS last_date,
  COUNT(DISTINCT m.obs_date) AS days_with_data
FROM mart_metrics_cohort AS m
JOIN dim_metric AS dm
  ON m.metric_id = dm.metric_id
  AND m.org_id = dm.org_id
  AND m.game_id = dm.game_id
  AND m.game_client_id = dm.game_client_id
WHERE dm.metric_name = 'D7 Retention'
  AND m.obs_date BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 30 DAY)
                   AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 7 DAY)
GROUP BY
  m.org_id,
  m.game_id,
  m.game_client_id,
  m.country
ORDER BY
  m.org_id,
  m.game_id,
  m.game_client_id,
  d7_retention DESC;
