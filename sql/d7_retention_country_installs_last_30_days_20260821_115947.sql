-- Question: What is the D7 retention by country for installs in the last 30 days?
-- Generated: 20260821_115947 by the NL-to-SQL agent

WITH
  params AS (
    SELECT
      DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 29 DAY) AS start_install_date,
      DATE_SUB(CURRENT_DATE("UTC"), INTERVAL 7 DAY) AS end_install_date
  ),
  installs AS (
    SELECT
      u.org_id,
      u.game_id,
      u.user_id,
      u.install_date,
      u.install_country_key
    FROM dim_user u
    CROSS JOIN params p
    WHERE u.is_current = TRUE
      AND u.install_date BETWEEN p.start_install_date AND p.end_install_date
  ),
  day7_activity AS (
    SELECT
      a.org_id,
      a.game_id,
      a.user_id
    FROM fact_user_activity_daily a
    CROSS JOIN params p
    WHERE a.days_since_install = 7
      AND a.event_date BETWEEN DATE_ADD(p.start_install_date, INTERVAL 7 DAY)
                          AND DATE_ADD(p.end_install_date, INTERVAL 7 DAY)
  )
SELECT
  i.org_id,
  i.game_id,
  c.country_name AS country,
  SAFE_DIVIDE(COUNT(DISTINCT a.user_id), COUNT(DISTINCT i.user_id)) AS d7_retention,
  MIN(i.install_date) AS first_date,
  MAX(i.install_date) AS last_date,
  COUNT(DISTINCT i.install_date) AS days_with_data
FROM installs i
LEFT JOIN day7_activity a
  ON a.org_id = i.org_id
 AND a.game_id = i.game_id
 AND a.user_id = i.user_id
LEFT JOIN dim_country c
  ON c.country_key = i.install_country_key
GROUP BY
  i.org_id,
  i.game_id,
  country;
