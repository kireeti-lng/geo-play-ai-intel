"""Run the NL-to-SQL agent over the fixture questions and score the results.

Why this exists: before it, every rule or check change was judged by generating a
few queries and reading them. That missed regressions, and three times a rule
change left the validator contradicting the rule. This gives one comparable
number per run so a change can be shown to help.

How to run it:
    python evals/run_evals.py                 -> all questions, no retries (cheap baseline)
    python evals/run_evals.py --retries 2     -> also measure the retry path
    python evals/run_evals.py --only d7_country,ecpm_trend
    python evals/run_evals.py --repeat 3      -> quantify run-to-run variance

Every run appends one JSON line per question to evals/results.jsonl.
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from geoplay.rules import GAME_ID
from geoplay.validate import build_fix_request, hard_problems, load_dictionary, validate

import sql_generation as agent_module

QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions.json")
RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.jsonl")

WINDOW_COLUMNS = ["first_date", "last_date", "days_with_data"]
TENANT_COLUMNS = ["org_id", "game_id", "game_client_id"]

# ---------------------------------------------------------------------------
# READ THE COMMAND LINE
# ---------------------------------------------------------------------------

args = sys.argv[1:]


def option(name, default):
    """Read --name value from the command line."""
    if name in args:
        return args[args.index(name) + 1]
    return default


retries = int(option("--retries", "0"))
repeat = int(option("--repeat", "1"))
only = option("--only", "")

# ---------------------------------------------------------------------------
# INSPECTING THE SQL
# ---------------------------------------------------------------------------


def cte_names(sql):
    """Names introduced by WITH ... AS ( ... )."""
    return {name.lower() for name in re.findall(r"(\w+)\s+AS\s*\(", sql, re.I)}


_DICT = load_dictionary()
_KNOWN_TABLES = {t.lower() for t in _DICT}
_KNOWN_COLUMNS = {c.lower() for cols in _DICT.values() for c in cols}


def tables_used(sql):
    """Real tables the query reads, excluding CTEs, functions and columns.

    EXTRACT(MONTH FROM event_date) also contains the word FROM, so a candidate
    that is a known column name is a column, not a table.
    """
    ctes = cte_names(sql)
    called = {name.lower() for name in re.findall(r"(\w+)\s*\(", sql)}
    aliases = {a.lower() for a in re.findall(r"\bAS\s+(\w+)", sql, re.I)}

    found = []
    for name in re.findall(r"(?:FROM|JOIN)\s+`?([A-Za-z_][\w.]*)`?", sql, re.I):
        bare = name.split(".")[-1].lower()
        if bare in ctes or bare in called or bare in aliases:
            continue
        if bare in _KNOWN_COLUMNS and bare not in _KNOWN_TABLES:
            continue
        found.append(bare)
    return sorted(set(found))


def score_expectations(sql, expected):
    """Compare the SQL against the mechanically checkable expectations.

    Returns a list of failure strings; empty means every expectation held.
    """
    failures = []
    lower = sql.lower()
    tables = tables_used(sql)

    if expected.get("window_columns"):
        missing = [c for c in WINDOW_COLUMNS if c not in lower]
        if missing:
            failures.append("missing window columns: " + ", ".join(missing))
    else:
        present = [c for c in WINDOW_COLUMNS if c in lower]
        if present:
            failures.append("window columns not wanted here: " + ", ".join(present))

    if expected.get("tenant_columns") and "org_id" not in lower:
        failures.append("no tenant columns")

    banned = [t for t in tables if t in expected.get("forbid_tables", [])]
    if banned:
        failures.append("forbidden table: " + ", ".join(banned))

    wanted = expected.get("expect_any_table", [])
    if wanted and not any(t in tables for t in wanted):
        failures.append(f"none of the expected tables {wanted} used, got {tables}")

    joins = len(re.findall(r"\bJOIN\b", sql, re.I))
    if "max_joins" in expected and joins > expected["max_joins"]:
        failures.append(f"{joins} joins, expected at most {expected['max_joins']}")

    ctes = len(cte_names(sql))
    if "max_ctes" in expected and ctes > expected["max_ctes"]:
        failures.append(f"{ctes} CTEs, expected at most {expected['max_ctes']}")

    return failures


# ---------------------------------------------------------------------------
# RUNNING THE AGENT
# ---------------------------------------------------------------------------


def generate(agent, question):
    """One agent invocation. Returns the SQL plus cost and latency."""
    started = time.time()
    result = asyncio.run(agent._agent.ainvoke({"messages": [{"role": "user", "content": question}]}))
    elapsed = time.time() - started

    messages = result["messages"]
    tokens_in = 0
    tokens_out = 0
    trips = 0
    for message in messages:
        usage = getattr(message, "usage_metadata", None) or {}
        if usage:
            trips = trips + 1
            tokens_in = tokens_in + usage.get("input_tokens", 0)
            tokens_out = tokens_out + usage.get("output_tokens", 0)

    text = agent_module.extract_response_text(result)
    sql = agent_module.extract_sql(text)
    return {
        "sql": sql,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "round_trips": trips,
        "seconds": round(elapsed, 1),
    }


def run_one(agent, entry):
    """Generate, score the first attempt, then optionally run the retry loop."""
    question = entry["question"]
    expected = entry["auto"]

    run = generate(agent, question)
    sql = run["sql"]

    first = {
        "checks": hard_problems(sql, GAME_ID),
        "expectations": score_expectations(sql, expected),
    }

    used_retries = 0
    while used_retries < retries:
        problems = hard_problems(sql, GAME_ID)
        if not problems:
            break
        used_retries = used_retries + 1
        follow_up = question + "\n\n" + build_fix_request(sql, problems)
        again = generate(agent, follow_up)
        sql = again["sql"]
        run["tokens_in"] = run["tokens_in"] + again["tokens_in"]
        run["tokens_out"] = run["tokens_out"] + again["tokens_out"]
        run["round_trips"] = run["round_trips"] + again["round_trips"]
        run["seconds"] = round(run["seconds"] + again["seconds"], 1)

    final = {
        "checks": hard_problems(sql, GAME_ID),
        "expectations": score_expectations(sql, expected),
        "review": validate(sql, GAME_ID).get("review", []),
    }

    return {
        "id": entry["id"],
        "question": question,
        "tables": tables_used(sql),
        "retries": used_retries,
        "first_pass_clean": not first["checks"] and not first["expectations"],
        "final_clean": not final["checks"] and not final["expectations"],
        "first": first,
        "final": final,
        "sql": sql,
        **{k: run[k] for k in ("tokens_in", "tokens_out", "round_trips", "seconds")},
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

with open(QUESTIONS_PATH, encoding="utf-8") as f:
    entries = json.load(f)["questions"]

if only:
    wanted = [name.strip() for name in only.split(",")]
    entries = [e for e in entries if e["id"] in wanted]

print(f"{len(entries)} question(s), repeat={repeat}, retries={retries}\n")

agent = agent_module.NLToSQLAgent()
rows = []
stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# Each row is written as soon as it completes. An earlier version only wrote at
# the end, so when the provider returned a credit error mid-run every completed
# question was lost.
results_file = open(RESULTS_PATH, "a", encoding="utf-8")

for pass_number in range(1, repeat + 1):
    for entry in entries:
        try:
            row = run_one(agent, entry)
        except Exception as error:
            # One question failing must not discard the questions already done.
            print(f"  [ERROR] {entry['id']:28} {type(error).__name__}: {str(error)[:110]}")
            continue

        row["pass"] = pass_number
        row["run_at"] = stamp
        rows.append(row)
        results_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        results_file.flush()

        flag = "PASS" if row["final_clean"] else "FAIL"
        first_flag = "first-pass" if row["first_pass_clean"] else "needed work"
        print(f"  [{flag}] {row['id']:28} {first_flag:11} "
              f"{row['tokens_in']:>7,} in  {row['seconds']:>5.1f}s  "
              f"retries={row['retries']}  {row['tables']}")
        for problem in row["final"]["expectations"]:
            print(f"           expectation: {problem}")
        for name in row["final"]["checks"]:
            for problem in row["final"]["checks"][name]:
                print(f"           check [{name}]: {problem}")

results_file.close()

if not rows:
    print("\nNo question completed. Nothing to score.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# SCORECARD
# ---------------------------------------------------------------------------

total = len(rows)
first_clean = sum(1 for r in rows if r["first_pass_clean"])
final_clean = sum(1 for r in rows if r["final_clean"])
tokens_in = sum(r["tokens_in"] for r in rows)
tokens_out = sum(r["tokens_out"] for r in rows)
seconds = sum(r["seconds"] for r in rows)

print()
print("=" * 68)
print(f"  first-pass clean : {first_clean}/{total}")
print(f"  final clean      : {final_clean}/{total}")
print(f"  tokens           : {tokens_in:,} in / {tokens_out:,} out")
print(f"  wall clock       : {seconds:.0f}s  ({seconds/total:.1f}s per question)")
print(f"  retries used     : {sum(r['retries'] for r in rows)}")
print("=" * 68)

# Table choice per question, which is where the known variance shows up.
if repeat > 1:
    print("\n  run-to-run table choice:")
    for entry in entries:
        picks = [tuple(r["tables"]) for r in rows if r["id"] == entry["id"]]
        distinct = len(set(picks))
        print(f"    {entry['id']:28} {distinct} distinct choice(s) over {len(picks)} runs")

print(f"\nwrote {len(rows)} row(s) to {RESULTS_PATH} as they completed")
