-- Question: How many new payers were there in the month of may?
-- Generated: 20260820_205940 by openai/gpt-5.2

WITH may_period AS (
  SELECT
    org_id,
    game_id,
    DATE_TRUNC(max_may_date, MONTH) AS period_start,
    LAST_DAY(DATE_TRUNC(max_may_date, MONTH), MONTH) AS period_end
  FROM (
    SELECT
      org_id,
      game_id,
      MAX(IF(EXTRACT(MONTH FROM event_date) = 5, event_date, NULL)) AS max_may_date
    FROM fact_purchases
    GROUP BY org_id, game_id
  )
  WHERE max_may_date IS NOT NULL
),
user_first_success AS (
  SELECT
    org_id,
    game_id,
    user_id,
    MIN(event_date) AS first_success_purchase_date
  FROM fact_purchases
  WHERE COALESCE(is_successful_purchase, FALSE)
  GROUP BY org_id, game_id, user_id
),
month_coverage AS (
  SELECT
    p.org_id,
    p.game_id,
    p.period_start,
    MIN(fp.event_date) AS first_date,
    MAX(fp.event_date) AS last_date,
    COUNT(DISTINCT fp.event_date) AS days_with_data
  FROM may_period p
  JOIN fact_purchases fp
    ON fp.org_id = p.org_id
   AND fp.game_id = p.game_id
   AND fp.event_date BETWEEN p.period_start AND p.period_end
  GROUP BY p.org_id, p.game_id, p.period_start
)
SELECT
  p.org_id,
  p.game_id,
  p.period_start,
  COUNT(DISTINCT IF(ufs.first_success_purchase_date BETWEEN p.period_start AND p.period_end, ufs.user_id, NULL)) AS new_payers,
  mc.first_date,
  mc.last_date,
  mc.days_with_data
FROM may_period p
LEFT JOIN user_first_success ufs
  ON ufs.org_id = p.org_id
 AND ufs.game_id = p.game_id
LEFT JOIN month_coverage mc
  ON mc.org_id = p.org_id
 AND mc.game_id = p.game_id
 AND mc.period_start = p.period_start
GROUP BY
  p.org_id,
  p.game_id,
  p.period_start,
  mc.first_date,
  mc.last_date,
  mc.days_with_data;
