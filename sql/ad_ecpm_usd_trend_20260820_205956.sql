-- Question: What is the Ad eCPM (USD) trend?
-- Generated: 20260820_205956 by openai/gpt-5.2

SELECT
  f.org_id,
  f.game_id,
  f.game_client_id,
  f.event_date,
  1000 * SAFE_DIVIDE(SUM(f.numerator), SUM(f.denominator)) AS ad_ecpm_usd
FROM fact_metrics_daily AS f
JOIN dim_metric AS m
  ON m.org_id = f.org_id
  AND m.game_id = f.game_id
  AND m.game_client_id = f.game_client_id
  AND m.metric_id = f.metric_id
WHERE m.metric_name = 'Ad eCPM (USD)' -- verify exact metric_name if needed
GROUP BY
  f.org_id,
  f.game_id,
  f.game_client_id,
  f.event_date
ORDER BY
  f.org_id,
  f.game_id,
  f.game_client_id,
  f.event_date;
