-- Question: How many sessions per DAU did we have till date?
-- Generated: 20260820_202601 by openai/gpt-5.2

WITH daily AS (
  SELECT
    org_id,
    game_id,
    game_client_id,
    event_date,
    SAFE_DIVIDE(
      SUM(sessions_count),
      COUNT(DISTINCT IF(COALESCE(has_session, FALSE), user_id, NULL))
    ) AS sessions_per_dau
  FROM fact_user_daily
  GROUP BY
    org_id,
    game_id,
    game_client_id,
    event_date
)
SELECT
  org_id,
  game_id,
  game_client_id,
  AVG(sessions_per_dau) AS sessions_per_dau,
  MIN(event_date) AS first_date,
  MAX(event_date) AS last_date,
  COUNT(*) AS days_with_data
FROM daily
GROUP BY
  org_id,
  game_id,
  game_client_id;
