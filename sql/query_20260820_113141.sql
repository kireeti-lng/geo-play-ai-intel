-- Question: How many new payers were there last week?
-- Generated: 20260820_113141 by openai/gpt-5.6-luna

SELECT
  COUNT(DISTINCT user_id) AS new_payers
FROM `fact_purchases`
WHERE is_successful_purchase = TRUE
  AND event_date >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY)), INTERVAL 7 DAY)
  AND event_date < DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))
  AND user_id IN (
    SELECT user_id
    FROM `fact_purchases`
    WHERE is_successful_purchase = TRUE
    GROUP BY user_id
    HAVING MIN(event_date) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY)), INTERVAL 7 DAY)
       AND MIN(event_date) < DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))
  );
