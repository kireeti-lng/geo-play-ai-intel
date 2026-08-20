"""Run the whole metadata -> SQL pipeline, in order.

Stages:
    1. scripts/data_dictionary.py          -> output/data_dictionary.json
    2. scripts/metric_catalogue_generator.py -> metric_catalogue/metric_catalogue.json
    3. scripts/sql_generation_simple.py    -> sql/query_<timestamp>.sql

Stage 1 costs many LLM calls, so it is skipped when its output already exists.
Stage 2 is free and deterministic, so it always runs.

How to run it:
    python run_pipeline.py
    python run_pipeline.py "Show ARPDAU by country for the last 7 days"
    python run_pipeline.py --refresh-dictionary "Show new payers last week"
"""

import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

DICT_SCRIPT = os.path.join(REPO_ROOT, "scripts", "data_dictionary.py")
METRIC_SCRIPT = os.path.join(REPO_ROOT, "scripts", "metric_catalogue_generator.py")
SQL_SCRIPT = os.path.join(REPO_ROOT, "scripts", "sql_generation_simple.py")

DICT_OUTPUT = os.path.join(REPO_ROOT, "output", "data_dictionary.json")
METRIC_OUTPUT = os.path.join(REPO_ROOT, "metric_catalogue", "metric_catalogue.json")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def say(text=""):
    """Print immediately.

    flush=True matters here: without it our own output stays buffered while
    the child scripts write straight to the terminal, so the stage banners
    would appear after the output they are meant to label.
    """
    print(text, flush=True)


def print_header(number, title):
    """Print a banner so it is obvious which stage is running."""
    say()
    say("=" * 70)
    say(f"STAGE {number}: {title}")
    say("=" * 70)


def run_script(script, extra_args=None):
    """Run one script with the same Python that is running this file.

    Returns True when the script exits successfully.
    """
    command = [sys.executable, script]
    if extra_args:
        command = command + extra_args

    # cwd is the repo root so every stage sees the same relative paths.
    result = subprocess.run(command, cwd=REPO_ROOT)
    return result.returncode == 0


def check_output(path, stage_name):
    """Stop the pipeline if a stage did not produce the file we expected."""
    if not os.path.exists(path):
        say(f"\nPipeline stopped: {stage_name} did not create {path}")
        sys.exit(1)
    say(f"Output ready: {path}")


# ---------------------------------------------------------------------------
# READ THE COMMAND LINE
# ---------------------------------------------------------------------------

arguments = sys.argv[1:]

refresh_dictionary = "--refresh-dictionary" in arguments
if refresh_dictionary:
    arguments.remove("--refresh-dictionary")

# Anything left over is the question. Empty means the SQL script uses its own default.
if arguments:
    question = arguments[0]
else:
    question = ""

# ---------------------------------------------------------------------------
# STAGE 1: DATA DICTIONARY
# ---------------------------------------------------------------------------

print_header(1, "Data dictionary")

if os.path.exists(DICT_OUTPUT) and not refresh_dictionary:
    say("Skipped: output/data_dictionary.json already exists.")
    say("Use --refresh-dictionary to rebuild it from the schema export.")
else:
    if not run_script(DICT_SCRIPT):
        say("\nPipeline stopped: the data dictionary stage failed.")
        sys.exit(1)

check_output(DICT_OUTPUT, "data dictionary")

# ---------------------------------------------------------------------------
# STAGE 2: METRIC CATALOGUE
# ---------------------------------------------------------------------------

print_header(2, "Metric catalogue")

if not run_script(METRIC_SCRIPT):
    say("\nPipeline stopped: the metric catalogue stage failed.")
    sys.exit(1)

check_output(METRIC_OUTPUT, "metric catalogue")

# ---------------------------------------------------------------------------
# STAGE 3: SQL GENERATION
# ---------------------------------------------------------------------------

print_header(3, "SQL generation")

if question:
    sql_args = [question]
else:
    sql_args = None

if not run_script(SQL_SCRIPT, sql_args):
    say("\nPipeline stopped: the SQL generation stage failed.")
    sys.exit(1)

say()
say("=" * 70)
say("Pipeline finished. Generated SQL is in the sql/ folder.")
say("=" * 70)
