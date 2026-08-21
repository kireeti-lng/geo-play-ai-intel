"""One JSONL line per generation run, so behaviour can be looked at over time.

Every number in the improvement plan had to be obtained by ad-hoc instrumentation
because nothing was recorded. This fixes that: each run appends a line to
telemetry.jsonl and nothing else changes.

Writing is best-effort. Telemetry must never be the reason a run fails, so any
error while recording is swallowed.
"""

import json
import os
import re
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TELEMETRY_PATH = os.path.join(REPO_ROOT, "telemetry.jsonl")


def tables_in(sql):
    """Table-ish names the query reads. Rough on purpose - this is a log."""
    ctes = {m.lower() for m in re.findall(r"(\w+)\s+AS\s*\(", sql, re.I)}
    called = {m.lower() for m in re.findall(r"(\w+)\s*\(", sql)}
    found = []
    for name in re.findall(r"(?:FROM|JOIN)\s+`?([A-Za-z_][\w.]*)`?", sql, re.I):
        bare = name.split(".")[-1].lower()
        if bare not in ctes and bare not in called:
            found.append(bare)
    return sorted(set(found))


def record(question, sql, model, problems=None, retries=0, seconds=None,
           tokens_in=None, tokens_out=None, round_trips=None, generator=""):
    """Append one line describing a completed run.

    Args:
        question: The natural-language question asked.
        sql: The SQL finally returned.
        model: Model slug used.
        problems: The validate() result, or None.
        retries: How many correction attempts were needed.
        seconds: Wall clock, when the caller measured it.
        tokens_in, tokens_out, round_trips: Cost, when the caller measured it.
        generator: "agent" or "simple".
    """
    problems = problems or {}

    line = {
        "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generator": generator,
        "model": model,
        "question": question,
        "retries": retries,
        "clean": not [k for k in problems if k not in ("review", "shape")],
        "checks_failed": sorted(k for k in problems if k not in ("review", "shape")),
        "review_count": len(problems.get("review", [])),
        "tables": tables_in(sql),
        "ctes": len(re.findall(r"\w+\s+AS\s*\(", sql, re.I)),
        "joins": len(re.findall(r"\bJOIN\b", sql, re.I)),
        "sql_lines": len([line for line in sql.splitlines() if line.strip()]),
        "seconds": seconds,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "round_trips": round_trips,
    }

    try:
        with open(TELEMETRY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let logging break a run

    return line


def summarise():
    """Read the log back and print a short summary. Returns the rows."""
    if not os.path.exists(TELEMETRY_PATH):
        print("No telemetry recorded yet.")
        return []

    rows = []
    with open(TELEMETRY_PATH, encoding="utf-8") as f:
        for text in f:
            text = text.strip()
            if text:
                rows.append(json.loads(text))

    if not rows:
        print("No telemetry recorded yet.")
        return rows

    clean = sum(1 for r in rows if r["clean"])
    retried = sum(1 for r in rows if r["retries"])
    print(f"{len(rows)} run(s) recorded")
    print(f"  clean            : {clean}/{len(rows)}")
    print(f"  needed a retry   : {retried}")

    counted = [r for r in rows if r.get("tokens_in")]
    if counted:
        total = sum(r["tokens_in"] for r in counted)
        print(f"  input tokens     : {total:,} over {len(counted)} measured run(s) "
              f"({total // len(counted):,} average)")

    # Which checks fail most often is the most useful thing in here.
    tally = {}
    for r in rows:
        for name in r["checks_failed"]:
            tally[name] = tally.get(name, 0) + 1
    if tally:
        print("  most common failures:")
        for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"    {name:20} {count}")

    return rows


if __name__ == "__main__":
    summarise()
