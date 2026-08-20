-- Question: What is the tutorial completion rate by platform for the last 14 days?
-- Generated: 20260820_120634 by openai/gpt-5.2

WITH metric_ids AS (
  SELECT DISTINCT metric_id
  FROM dim_metric
  WHERE metric_name = 'Tutorial Completion Rate'
),
base AS (
  SELECT
    event_date,
    platform,
    numerator,
    denominator
  FROM fact_metrics_daily
  WHERE event_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 13 DAY) AND CURRENT_DATE()
    AND metric_id IN (SELECT metric_id FROM metric_ids)
)
SELECT
  platform,
  SAFE_DIVIDE(SUM(numerator), SUM(denominator)) AS tutorial_completion_rate,
  SUM(numerator) AS tutorial_completions,
  SUM(denominator) AS tutorial_starters,
  COUNT(DISTINCT event_date) AS days_in_window
FROM base
GROUP BY platform
ORDER BY platform;
