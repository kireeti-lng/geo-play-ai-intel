"""Deterministic checks on generated SQL.

Prompt rules are only a request; the model may ignore them. These checks read
the finished SQL and report what is actually wrong, without needing a warehouse.

Each check returns a list of problem strings. An empty list means it passed.
"""

import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH = os.path.join(REPO_ROOT, "output", "data_dictionary.json")

# Functions from other SQL dialects. Seeing one means the model drifted away
# from BigQuery, which is how the first DATEADD(...) bug showed up.
# IFNULL, SAFE_MULTIPLY and DATE_DIFF are valid BigQuery and are NOT listed.
WRONG_DIALECT = [
    "DATEADD", "GETDATE", "SYSDATE", "NVL(", "ISNULL(",
    "TOP ", "NOW()", "STRFTIME", "TO_CHAR(",
]

# Window columns the output-shape rule asks for.
REQUIRED_WINDOW_COLUMNS = ["first_date", "last_date", "days_with_data"]

# Ratio-style names that must never be summed.
RATIO_HINTS = ["arpu", "arppu", "arpdau", "ecpm", "_rate", "retention", "conversion"]

# Date columns that must not be wrapped in a function inside WHERE or ON.
DATE_COLUMNS = ["event_date", "full_date", "install_date", "obs_date", "period_start"]

# Columns identifying the tenant a row belongs to.
TENANT_COLUMNS = ["org_id", "game_id", "game_client_id"]

# Flags that describe who is eligible, so they belong on the denominator only.
ELIGIBILITY_HINTS = ["has_session", "is_active", "is_payer", "is_current"]

# BigQuery dryRun needs warehouse credentials, which this repo does not have.
# The check is registered but inert, so it can be switched on without
# restructuring validate().
DRY_RUN_ENABLED = False


def load_dictionary():
    """Return {table_name: set of column names} from the data dictionary."""
    with open(DICT_PATH, encoding="utf-8") as f:
        columns = json.load(f)["columns"]

    tables = {}
    for column in columns:
        table = column["table_name"]
        if table not in tables:
            tables[table] = set()
        tables[table].add(column["column_name"])
    return tables


def strip_comments(sql):
    """Remove -- comment lines so they are not mistaken for SQL."""
    lines = []
    for line in sql.split("\n"):
        if not line.strip().startswith("--"):
            lines.append(line)
    return "\n".join(lines)


def find_cte_names(sql):
    """Names defined by WITH ... AS ( ... ), which are not real tables."""
    return {name.lower() for name in re.findall(r"(\w+)\s+AS\s*\(", sql, re.I)}


def check_tables(sql, tables):
    """Every table read must exist in the data dictionary or be a CTE.

    EXTRACT(MONTH FROM event_date) also contains the word FROM, so any candidate
    that is a known column name is skipped rather than reported as a table.
    """
    known_tables = {t.lower() for t in tables}
    known_columns = set()
    for cols in tables.values():
        known_columns.update(c.lower() for c in cols)

    ctes = find_cte_names(sql)
    # Columns computed inside a CTE, e.g. MIN(event_date) AS first_purchase_date.
    aliases = {a.lower() for a in re.findall(r"\bAS\s+(\w+)", sql, re.I)}
    # Function calls, e.g. the MAX in EXTRACT(YEAR FROM MAX(event_date)).
    called = {name.lower() for name in re.findall(r"(\w+)\s*\(", sql)}

    problems = []
    for name in re.findall(r"(?:FROM|JOIN)\s+`?([A-Za-z_][\w.]*)`?", sql, re.I):
        bare = name.split(".")[-1].lower()
        if bare in called:
            continue
        if bare in ctes or bare in known_tables:
            continue
        if bare in known_columns or bare in aliases:
            continue  # a column inside EXTRACT(... FROM col), not a table
        problems.append(f"unknown table: {name}")

    return sorted(set(problems))


def check_columns(sql, tables):
    """Flag identifiers that look like columns but exist in no table.

    Deliberately conservative: only words that appear nowhere in the schema and
    are not CTE names or aliases get reported, so aliases do not cause noise.
    """
    known = set()
    for cols in tables.values():
        known.update(c.lower() for c in cols)
    # Table names appear in FROM/JOIN clauses and are not columns.
    known.update(t.lower() for t in tables)

    ctes = find_cte_names(sql)
    aliases = {a.lower() for a in re.findall(r"\bAS\s+(\w+)", sql, re.I)}
    # A word followed by "(" is a function call, not a column. This covers every
    # BigQuery function without needing to list them.
    called = {name.lower() for name in re.findall(r"(\w+)\s*\(", sql)}

    problems = []
    for word in re.findall(r"\b([a-z][a-z0-9_]{2,})\b", sql.lower()):
        if word in known or word in ctes or word in aliases or word in called:
            continue
        if "_" not in word:
            continue  # single words are usually keywords or aliases
        problems.append(f"unknown column-like name: {word}")

    return sorted(set(problems))


def check_dialect(sql):
    """Flag functions that belong to other SQL dialects."""
    upper = sql.upper()
    problems = []
    for bad in WRONG_DIALECT:
        if bad in upper:
            problems.append(f"not BigQuery syntax: {bad.strip()}")
    return problems


def check_game_filter(sql, game_id):
    """When a game is configured, the query must filter on it."""
    if not game_id:
        return []
    if re.search(r"game_id\s*=", sql, re.I):
        return []
    return ["missing game_id filter (GAME_ID is set, so results blend games)"]


def is_time_series(sql):
    """True when the result already has one row per date.

    A per-date result needs no window columns: the date column is the window.
    Detected by a bare date column in the final GROUP BY, with no DATE_TRUNC
    rolling it up to a coarser period.
    """
    tail = sql[sql.lower().rfind("group by"):].lower()
    if not tail:
        return False
    grouped_by_date = re.search(r"\b\w*\.?(event_date|full_date)\b", tail)
    rolled_up = re.search(r"(date_trunc|month_start|period_start|week_start)", tail)
    return bool(grouped_by_date) and not bool(rolled_up)


def check_window_columns(sql):
    """Aggregated results must show the window they cover.

    Skipped for a per-date time series, where the date column already shows it.
    """
    if is_time_series(sql):
        return []

    lower = sql.lower()
    missing = [c for c in REQUIRED_WINDOW_COLUMNS if c not in lower]
    if missing:
        return ["missing window column: " + ", ".join(missing)]
    return []


def check_pruning(sql):
    """A date column wrapped in a function inside WHERE or ON kills pruning."""
    problems = []
    # Look at each WHERE / ON clause up to the next major keyword.
    clauses = re.findall(
        r"\b(?:WHERE|ON)\b([\s\S]*?)(?=\b(?:GROUP BY|ORDER BY|HAVING|WHERE|ON|SELECT|LIMIT)\b|\)|$)",
        sql, re.I,
    )
    for clause in clauses:
        for col in DATE_COLUMNS:
            hit = re.search(r"(EXTRACT|DATE_TRUNC)\s*\([^()]*\b" + col + r"\b", clause, re.I)
            if hit:
                problems.append(
                    f"{hit.group(1).upper()}(... {col} ...) inside WHERE/ON stops "
                    "partition pruning - compare the raw column to a date range instead"
                )
    return sorted(set(problems))


def check_tenant_grouping(sql, game_id):
    """With no single game configured, a result must not blend tenants.

    Enforces the TENANT SCOPE rule in the case the game filter check cannot
    cover: when GAME_ID is blank the query has to GROUP BY the tenant columns
    instead. Only fires when the query aggregates and the table actually has
    those columns.
    """
    if game_id:
        return []  # check_game_filter covers the configured case

    if not re.search(r"\bGROUP BY\b", sql, re.I):
        return []  # nothing aggregated, nothing to blend

    tables = load_dictionary()
    reading = [t for t in tables if re.search(r"\b" + t + r"\b", sql, re.I)]
    if not reading:
        return []

    # Which tenant columns exist on any table this query reads?
    available = set()
    for table in reading:
        for column in TENANT_COLUMNS:
            if column in tables[table]:
                available.add(column)
    if not available:
        return []

    tail = sql[sql.lower().rfind("group by"):]
    missing = [c for c in sorted(available) if not re.search(r"\b" + c + r"\b", tail, re.I)]
    if missing:
        return ["not grouped by " + ", ".join(missing)
                + " - the result blends tenants (set GAME_ID to filter instead)"]
    return []


def check_numerator_filter(sql):
    """An eligibility filter belongs on the denominator, not the numerator.

    SUM(IF(has_session, revenue, 0)) discards revenue booked on a day with no
    session, which understates the metric. Enforces NUMERATOR AND DENOMINATOR.
    """
    problems = []
    pattern = r"SUM\s*\(\s*(?:IF|CASE\s+WHEN)\s*\(?\s*([\w.()]*(?:" + "|".join(ELIGIBILITY_HINTS) + r")[\w.()]*)"
    for flag in re.findall(pattern, sql, re.I):
        problems.append(
            f"SUM(IF({flag.strip()}, ...)) filters the numerator by an eligibility "
            "flag - filter the denominator only and sum the numerator whole"
        )
    return sorted(set(problems))


def check_complexity(sql):
    """Report shape so bloat is visible. Informational, never a failure."""
    ctes = len(find_cte_names(sql))
    joins = len(re.findall(r"\bJOIN\b", sql, re.I))
    lines = len([line for line in sql.splitlines() if line.strip()])

    if ctes <= 2 and joins <= 2:
        return []
    return [f"shape: {ctes} CTEs, {joins} joins, {lines} lines "
            "- check every table and CTE is needed"]


def check_dry_run(sql):
    """Placeholder for a BigQuery dryRun check.

    dryRun validates a query and resolves every identifier without executing it
    or being billed, which would catch the wrong-but-valid SQL these text checks
    cannot see. It needs warehouse credentials, so this returns nothing until
    DRY_RUN_ENABLED is switched on and the client is wired in here.
    """
    if not DRY_RUN_ENABLED:
        return []
    return []


def check_summed_ratios(sql):
    """SUM() over a ratio-looking column is an aggregation error."""
    problems = []
    for inner in re.findall(r"SUM\s*\(([^()]*)\)", sql, re.I):
        low = inner.lower()
        for hint in RATIO_HINTS:
            if hint in low:
                problems.append(f"SUM over a ratio: SUM({inner.strip()})")
                break
    return sorted(set(problems))


def check_fanout_count(sql):
    """Flag COUNT(*) aliased as if it counted distinct entities.

    A join from a per-entity table back to a per-day table gives one row per
    day, so COUNT(*) counts rows. When the alias claims users or entities, the
    number is silently inflated. Catches the shape that made one ARPU query
    understate by half.
    """
    # Only a join that matches on the entity itself re-expands the rows. A
    # CROSS JOIN to a one-row table, or a join on dates, does not - so those
    # must not be flagged.
    joins_on_entity = re.search(
        r"\bJOIN\b[\s\S]{0,400}?\bON\b[\s\S]{0,400}?"
        r"(user_id|player_id|payer_id)\s*=\s*\w+\.(user_id|player_id|payer_id)",
        sql, re.I,
    )
    if not joins_on_entity:
        return []

    problems = []
    for alias in re.findall(r"COUNT\s*\(\s*\*\s*\)\s+AS\s+(\w+)", sql, re.I):
        low = alias.lower()
        if any(word in low for word in ("user", "unique", "distinct", "payer", "player")):
            problems.append(
                f"COUNT(*) AS {alias} counts rows, not entities, because the "
                "query joins on the entity column - use COUNT(DISTINCT <column>)"
            )
    return sorted(set(problems))


def check_assumed_values(sql):
    """List string literals the query compares a column against.

    We supply column names and descriptions but never the values stored in them,
    so every such literal is a guess. A wrong one returns zero rows silently.
    These are reported for review, not treated as errors.
    """
    found = []
    # column = 'literal'  and  column IN ('a', 'b')
    for col, val in re.findall(r"([\w.]+)\s*=\s*'([^']*)'", sql):
        found.append(f"{col} = '{val}'")
    for col, vals in re.findall(r"([\w.]+)\s+IN\s*\(\s*('[^)]*)\)", sql, re.I):
        found.append(f"{col} IN ({vals.strip()})")

    if not found:
        return []
    return ["unverified value assumption: " + f for f in sorted(set(found))]


def validate(sql, game_id=""):
    """Run every check and return {check name: [problems]} for failures only."""
    body = strip_comments(sql)
    tables = load_dictionary()

    results = {
        "tables": check_tables(body, tables),
        "columns": check_columns(body, tables),
        "dialect": check_dialect(body),
        "game filter": check_game_filter(body, game_id),
        "window columns": check_window_columns(body),
        "summed ratios": check_summed_ratios(body),
        "fan-out count": check_fanout_count(body),
        "pruning": check_pruning(body),
        "tenant grouping": check_tenant_grouping(body, game_id),
        "numerator filter": check_numerator_filter(body),
        "dry run": check_dry_run(body),
        "review": check_assumed_values(body),
        "shape": check_complexity(body),
    }
    return {name: found for name, found in results.items() if found}


# These describe the query for a human to weigh rather than reporting a defect,
# so they must never trigger a retry. "review" lists guessed literal values;
# "shape" reports CTE and join counts.
INFORMATIONAL = ["review", "shape"]


def hard_problems(sql, game_id=""):
    """Only the problems worth asking the model to fix."""
    found = validate(sql, game_id)
    return {k: v for k, v in found.items() if k not in INFORMATIONAL}


def build_fix_request(sql, problems):
    """Ask for a corrected query, quoting exactly what is wrong with this one."""
    lines = []
    for name in problems:
        for problem in problems[name]:
            lines.append(f"- {problem}")

    return (
        "The SQL below was generated for that question but failed these checks:\n"
        + "\n".join(lines)
        + "\n\nRewrite it so every check passes. Change nothing else: keep the "
        "same tables, the same metric and the same output columns otherwise.\n\n"
        + sql
    )


def report(sql, game_id=""):
    """Print the validation result. Returns True when everything passed."""
    problems = validate(sql, game_id)

    if not problems:
        print("Validation: all checks passed")
        return True

    print("Validation found issues:")
    for name in problems:
        for problem in problems[name]:
            print(f"  [{name}] {problem}")
    return False
