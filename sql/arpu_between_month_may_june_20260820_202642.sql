-- Question: What is ARPU in between the month of may and june?
-- Generated: 20260820_202642 by openai/gpt-5.2

WITH month_presence AS (
  SELECT
    org_id,
    game_id,
    game_client_id,
    EXTRACT(YEAR FROM event_date) AS yr,
    MAX(IF(EXTRACT(MONTH FROM event_date) = 5, 1, 0)) AS has_may,
    MAX(IF(EXTRACT(MONTH FROM event_date) = 6, 1, 0)) AS has_june
  FROM fact_user_daily
  GROUP BY 1, 2, 3, 4
),
chosen_year AS (
  SELECT
    org_id,
    game_id,
    game_client_id,
    MAX(yr) AS yr
  FROM month_presence
  WHERE has_may = 1 AND has_june = 1
  GROUP BY 1, 2, 3
)
SELECT
  fud.org_id,
  fud.game_id,
  fud.game_client_id,
  DATE_TRUNC(fud.event_date, MONTH) AS period_start,
  SAFE_DIVIDE(
    SUM(COALESCE(fud.revenue_iap_usd, 0) + COALESCE(fud.ad_revenue_usd, 0)),
    COUNT(DISTINCT IF(COALESCE(fud.has_session, FALSE), fud.user_id, NULL))
  ) AS arpu,
  MIN(fud.event_date) AS first_date,
  MAX(fud.event_date) AS last_date,
  COUNT(DISTINCT fud.event_date) AS days_with_data
FROM fact_user_daily AS fud
JOIN chosen_year AS cy
  ON fud.org_id = cy.org_id
 AND fud.game_id = cy.game_id
 AND fud.game_client_id = cy.game_client_id
WHERE fud.event_date BETWEEN DATE(cy.yr, 5, 1) AND LAST_DAY(DATE(cy.yr, 6, 1), MONTH)
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;
