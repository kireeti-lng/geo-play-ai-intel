-- Question: What is the tutorial completion rate by platform for the last 14 days?
-- Generated: 20260820_113821 by openai/gpt-5.6-luna

SELECT
  platform,
  COUNT(DISTINCT IF(LOWER(ftue_event_type) = 'completion', user_id, NULL)) AS tutorial_completers,
  COUNT(DISTINCT IF(LOWER(ftue_event_type) = 'start', user_id, NULL)) AS tutorial_starters,
  SAFE_DIVIDE(
    COUNT(DISTINCT IF(LOWER(ftue_event_type) = 'completion', user_id, NULL)),
    COUNT(DISTINCT IF(LOWER(ftue_event_type) = 'start', user_id, NULL))
  ) AS tutorial_completion_rate
FROM fact_ftue_steps
WHERE event_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 13 DAY) AND CURRENT_DATE()
GROUP BY platform
ORDER BY platform;
