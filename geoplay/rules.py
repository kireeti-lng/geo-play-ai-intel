"""The SQL rules, in one place.

Both generators read from here so they cannot drift apart:

    scripts/sql_generation.py         via geoplay/tools.py
    scripts/sql_generation_simple.py  directly

Pure standard library on purpose - the simple script must not need langchain.
"""

import os

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

SQL_DIALECT = "BigQuery standard SQL"

# Day boundaries. CURRENT_DATE() is UTC unless told otherwise, and the
# retention definitions all assume a declared reporting timezone.
REPORTING_TIMEZONE = "UTC"

# Set GAME_ID in .env to pin every query to one game. Left blank, queries must
# instead group by the tenant columns so games are never silently blended.
GAME_ID = (os.environ.get("GAME_ID") or "").strip()

# Columns that identify who the data belongs to.
TENANT_COLUMNS = ["org_id", "game_id", "game_client_id"]

BASE_RULES = """
APPROACH
- Work from the question, not from habit. Before writing anything, settle what
  is being asked: which metric, for which entity, at which grain, over which
  period.
- Then read that metric's definition to learn its numerator, its denominator,
  and which records are eligible.
- Then scan the table list for columns that ALREADY hold those inputs. The
  metadata you are given is complete. If the warehouse already stores a value,
  use that column instead of deriving it - deriving something that is already
  stored is slower, and it is where wrong answers come from.
- Judge your query on three things, in this order: is it CORRECT, is it SIMPLE
  enough for a non-expert to check, and is it EFFECTIVE - does it read the least
  data needed to answer.
- Before returning, read the question once more and confirm the final SELECT
  answers exactly that, and nothing more.

CHOOSING THE TABLE
- There is usually a purpose-built table for the subject. Retention lives in
  fact_retention_daily, ad events in fact_ad_events, sessions in fact_sessions,
  purchases in fact_purchases, daily per-user totals in fact_user_daily. Look
  for that table before reaching for anything generic.
- Prefer a table whose columns are named for the business meaning over one keyed
  by a generic metric_id, because the latter needs a lookup to resolve the id
  and an assumed name string to match on.
- Decide which SINGLE table already holds everything the question needs.
- Prefer the table that holds the metric's inputs as named columns. If one table
  contains the inputs for both the numerator and the denominator, use that table
  on its own.
- If one GROUP BY over one table answers the question, that is the answer.
- Do not join a table unless the query needs a column from it, and do not add a
  CTE that only wraps a single SELECT.
- Extra tables, extra CTEs and extra columns read as a mistake even when the
  arithmetic is right.

OUTPUT SHAPE
- The final SELECT must align exactly with what the user asked for: the metric
  they named, any dimension they asked to break it down by, and the tenant
  columns. Nothing else. Returning anything extra reads as the query having
  misunderstood the question, even when every number in it is correct.
- That means no intermediate values such as the numerator or the denominator,
  and no display or formatting columns such as a month name. Formatting belongs
  to the dashboard, not the query.
- Add a second metric only when it is genuinely required to produce the
  requested one and cannot be written inline. Never add one for context.
- If the result is aggregated over a period (one row per month, or a single
  total), also return the window covered: first_date, last_date and
  days_with_data. They show what the answer covers.
- If the result is already a time series with one row per date, do NOT add those
  columns. The date column already shows the window.
- When the question names more than one month or period, return ONE ROW PER
  PERIOD, with the period start as a column. Only collapse them into a single
  combined figure if the question explicitly asks for a combined total.

TIME RANGE
- Never invent a time range. If the question states no period - "trend", "over
  time", "by month" - cover all the data available and add no date filter.
  Do not silently narrow to the last 90 days or any other default.
- Resolve every relative or partial date phrase into explicit dates in the SQL.
- If the question names a month or period with no year, use the most recent
  occurrence present in the data, and let first_date and last_date reveal it.
- When the question spans several months, only accept a year in which EVERY
  requested month is present, so a year holding June but not May is not chosen
  for a May-to-June question.
- Always filter dates with a range predicate on the raw column:
      WHERE event_date BETWEEN <start> AND <end>
  Compute the start and end first, then compare the raw column to them.
- Never wrap a date column in a function inside WHERE or a JOIN condition.
  Writing
      WHERE EXTRACT(YEAR FROM event_date) = 2026
  stops the warehouse pruning partitions and scans the whole table. EXTRACT and
  DATE_TRUNC are fine in SELECT and GROUP BY.
- Evaluate day boundaries in {timezone}.

AGGREGATION SAFETY
- Classify each metric as additive, semi-additive, or non-additive first.
- Never SUM a ratio or percentage such as ARPU, ARPPU, ARPDAU, retention or
  conversion rates.
- Never SUM daily distinct-user counts across days, including DAU, WAU, MAU,
  unique users and unique payers.
- For a period-level ratio, compute it at the daily grain first, then aggregate
  across time with AVG unless the question asks for something else.
- Never approximate one metric from another: not MAU from DAU, not LTV from
  ARPU, not retention from DAU deltas.

COUNTING AND JOINS
- A join from a per-entity table back to a per-day table produces one row per
  day, not per entity. After any such join, COUNT(*) counts rows, not entities.
- To count entities always use COUNT(DISTINCT <entity column>), never COUNT(*).
- Prefer computing a distinct count in a single pass over the daily table
  instead of de-duplicating into a CTE and joining back to it.
- A versioned dimension can hold several rows per business key. Joining one
  without first reducing it to a single row per key multiplies every measure it
  touches. Reduce it first, or avoid the join.

NUMERATOR AND DENOMINATOR
- An eligibility filter such as "active users" defines the DENOMINATOR
  population. Do NOT apply it to the numerator as well.
- For a revenue-per-user metric the numerator is ALL revenue recorded in the
  window. Writing SUM(IF(has_session, revenue, 0)) silently discards revenue
  booked on a day with no session, which understates the metric.
- Filter the denominator, sum the numerator whole, then divide.
- Treat a nullable boolean as false explicitly, for example
  COALESCE(has_session, FALSE), so NULL does not quietly change the population.

COLUMN VALUES ARE UNKNOWN
- You are given column names and descriptions. You are NOT given the values
  stored in them, and no sample rows.
- Never invent a literal to compare against. A description reading "such as
  impression, click, completion" does not tell you the exact stored string: it
  could be 'impression', 'IMPRESSION' or 'ad_impression'.
- A wrong literal returns zero rows or a NULL metric with no error, which is
  worse than not answering at all.
- Where a column already counts or sums the thing you need, use that column
  instead of filtering a category column on a guessed value.
- Boolean and numeric columns are safe to test directly; it is only category and
  name strings whose values you cannot know.
- When a value filter is genuinely unavoidable, put it in ONE obvious place near
  the top of the query and mark it with a comment, so a reader can correct it in
  a single edit.

CORRECTNESS
- Use only the tables and columns listed below. Never invent a name.
- Compute any named metric exactly as its definition states, applying the
  numerator and denominator it specifies.
- Divide with SAFE_DIVIDE so a zero denominator yields NULL rather than an error.
- Write {dialect}.
""".strip()


def build_reminder():
    """The few rules that matter most, to repeat AFTER the schema listing.

    The schema is ~109,000 characters. Anything stated before it is a long way
    back by the time the model finishes reading, so the constraints that get
    dropped most often are restated here where they are still fresh.
    """
    tenant_list = ", ".join(TENANT_COLUMNS)
    return (
        "BEFORE YOU WRITE, RE-CHECK THESE\n"
        "1. Build the metric from the table that holds its real business columns.\n"
        "   A table keyed by metric_id needs an id lookup and an assumed name\n"
        "   string to match on - use the named columns instead where they exist.\n"
        "2. The final SELECT must contain only what was asked, plus "
        f"{tenant_list}.\n"
        "3. Add first_date, last_date and days_with_data unless the result is\n"
        "   already one row per date.\n"
        "4. Do not invent a date range, and do not wrap a date column in a\n"
        "   function inside WHERE or ON.\n"
        "5. Do not compare a column to a string value you were not given.\n"
        "6. Fewest tables, fewest joins, fewest CTEs that answer correctly."
    )


def build_rules():
    """Return the full rule text, including the tenant rules."""
    rules = BASE_RULES.format(
        timezone=REPORTING_TIMEZONE,
        dialect=SQL_DIALECT,
    )

    tenant_list = ", ".join(TENANT_COLUMNS)

    if GAME_ID:
        scope = (
            f"- This warehouse holds several games. Filter every table that has a\n"
            f"  game_id column with game_id = '{GAME_ID}'.\n"
            f"- Carry {tenant_list} through the query and return them, so the\n"
            "  reader can see exactly whose data the answer describes.\n"
        )
    else:
        scope = (
            f"- Rows belong to a tenant, identified by {tenant_list}.\n"
            "- No single game is configured, so never aggregate across tenants:\n"
            f"  GROUP BY whichever of {tenant_list} the table has, and return\n"
            "  them alongside the metric. Aggregating without them blends\n"
            "  different games into one number.\n"
        )

    # Resolving a reference date once, globally, quietly drops any tenant whose
    # data ends earlier than the winning date. It has to be resolved per tenant.
    scope = scope + (
        "- When a date or year has to be discovered from the data, resolve it\n"
        f"  separately for each tenant: GROUP that query BY {tenant_list} and\n"
        "  JOIN it back on those same columns. Never resolve it once as a single\n"
        "  global value or scalar subquery, because a tenant whose data ends\n"
        "  earlier would return no rows and look inactive."
    )

    return rules + "\n\nTENANT SCOPE\n" + scope
