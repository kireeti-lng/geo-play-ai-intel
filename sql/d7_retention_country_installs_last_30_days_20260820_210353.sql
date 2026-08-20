-- Question: What is the D7 retention by country for installs in the last 30 days?
-- Generated: 20260820_210353 by the NL-to-SQL agent

WITH cohort AS (
  SELECT
    org_id,
    game_id,
    game_client_id,
    user_id,
    install_date,
    primary_country AS country
  FROM dim_user_profile
  WHERE install_date BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 29 DAY)
    AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 7 DAY)
)
SELECT
  c.org_id,
  c.game_id,
  c.game_client_id,
  c.country,
  SAFE_DIVIDE(
    COUNT(DISTINCT IF(COALESCE(ud.has_session, FALSE), c.user_id, NULL)),
    COUNT(DISTINCT c.user_id)
  ) AS d7_retention,
  MIN(c.install_date) AS first_date,
  MAX(c.install_date) AS last_date,
  COUNT(DISTINCT c.install_date) AS days_with_data
FROM cohort c
LEFT JOIN fact_user_daily ud
  ON ud.org_id = c.org_id
 AND ud.game_id = c.game_id
 AND ud.game_client_id = c.game_client_id
 AND ud.user_id = c.user_id
 AND ud.event_date = DATE_ADD(c.install_date, INTERVAL 7 DAY)
 AND ud.event_date BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 22 DAY) AND CURRENT_DATE('UTC')
GROUP BY 1,2,3,4;
