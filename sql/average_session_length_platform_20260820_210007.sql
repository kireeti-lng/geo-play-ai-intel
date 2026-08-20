-- Question: What is the average session length by platform?
-- Generated: 20260820_210007 by openai/gpt-5.2

SELECT
  org_id,
  game_id,
  platform,
  SAFE_DIVIDE(SUM(session_duration_sec), COUNT(session_id)) AS avg_session_length,
  MIN(event_date) AS first_date,
  MAX(event_date) AS last_date,
  COUNT(DISTINCT event_date) AS days_with_data
FROM fact_sessions
GROUP BY
  org_id,
  game_id,
  platform;
