"""Turn a natural-language question into SQL, using the repo's own metadata as context.

Flow:
    User question -> load metric_catalogue.json + data_dictionary.json
                  -> build context -> ask the LLM -> print SQL -> save to sql/

How to run it:
    python scripts/sql_generation_simple.py                  -> uses QUESTION below
    python scripts/sql_generation_simple.py "your question"  -> uses that question instead
"""

import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

# Make the repo root importable so `geoplay` resolves when run as a script.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geoplay.rules import GAME_ID, build_rules
from geoplay.validate import build_fix_request, hard_problems, report

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Paths are built from this file's location, not the current folder,
# so the script works no matter where you run it from.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRIC_PATH = os.path.join(REPO_ROOT, "metric_catalogue", "metric_catalogue.json")
DICT_PATH = os.path.join(REPO_ROOT, "output", "data_dictionary.json")

# Every generated query is saved here, one file per run.
SQL_DIR = os.path.join(REPO_ROOT, "sql")

# The saved filename is built from the question. These words add nothing to a
# filename, so they are dropped, and the name is capped at a few words.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do", "does",
    "for", "from", "get", "give", "had", "has", "have", "how", "i", "in", "is",
    "it", "many", "me", "much", "my", "of", "on", "or", "our", "over", "per",
    "show", "tell", "that", "the", "their", "there", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "with",
}
SLUG_MAX_WORDS = 8

MODEL = "openai/gpt-5.2"

# Ask your question here. A question passed on the command line overrides this.
QUESTION = "Show ARPDAU by country for the last 7 days."

# How many times to send failed checks back for correction before giving up.
MAX_FIX_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# LOADING
# ---------------------------------------------------------------------------


def load_json(path):
    """Read one JSON file and return it as a dictionary."""
    if not os.path.exists(path):
        print(f"Missing file: {path}")
        print("Run scripts/data_dictionary.py and scripts/metric_catalogue_generator.py first.")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CONTEXT BUILDING
# ---------------------------------------------------------------------------


def group_columns_by_table(columns):
    """Turn the flat column list into {table_name: [column rows]}."""
    tables = {}
    for column in columns:
        table_name = column["table_name"]
        if table_name not in tables:
            tables[table_name] = []                      # are we seeing this table for the first time? if yes create a new list for it
        tables[table_name].append(column)                # if the table already exists, append the column to the list of columns for that table
    return tables


#   Iterates over each table and its columns and creates a formatted string representation of the schema for the prompt.
def build_schema_text(columns):
    """Render the data dictionary as compact, readable lines for the prompt."""
    tables = group_columns_by_table(columns)

    lines = []
    for table_name in sorted(tables):
        lines.append(f"TABLE {table_name}")
        for column in tables[table_name]:
            lines.append(f"  - {column['column_name']}: {column['description']}")
        lines.append("")

    return "\n".join(lines)

#   Iterates over each metric and creates a formatted string representation for the prompt.
def build_metric_text(metrics):
    """Render the metric catalogue as 'name: definition' lines for the prompt."""
    lines = []
    for metric in metrics:
        lines.append(f"{metric['metric_name']}: {metric['definition']}")
    return "\n".join(lines)

#  Takes raw jso/dictionary records from the data dictionary and metric catalogue and combines them into a single system prompt for the LLM.
def build_system_prompt(schema_text, metric_text):
    """Combine the shared rules, the schema and the metric definitions.

    The rules come from geoplay/rules.py so this script and the agent version
    in sql_generation.py always ask for exactly the same thing.
    """
    return f"""
You are a SQL generator for a mobile games analytics warehouse.
Write one query that answers the user's question.
Return only the SQL query. No explanation, no markdown, no code fences.

{build_rules()}

AVAILABLE TABLES
{schema_text}

METRIC DEFINITIONS
{metric_text}
""".strip()


# ---------------------------------------------------------------------------
# SQL GENERATION
# ---------------------------------------------------------------------------

# It cleans up the raw text returned by the LLM so it becomes valid, runnable SQL. It removes any code fences the model may add, and ensures the query ends with a single semicolon.
def clean_sql(text):
    """Strip code fences the model may add and end with a single semicolon."""
    sql = text.strip()

    # Remove a wrapping ```sql ... ``` block if there is one.
    if sql.startswith("```"):
        lines = sql.split("\n")
        lines = lines[1:]                      # drop the opening ``` line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]                 # drop the closing ``` line
        sql = "\n".join(lines).strip()

    return sql.rstrip(";") + ";"


def generate_sql(client, question, system_prompt):
    """Send the question plus context to the model and return the SQL."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    return clean_sql(response.choices[0].message.content)


# It converts human-readable question into a short, safe and readable string suitable for a file name.
def make_slug(question):
    """Turn a question into a short, readable filename part.

    "What is ARPU for the last 30 days?" -> "arpu_last_30_days"
    """
    # Keep letters and digits, turn everything else into a space.
    cleaned = ""
    for character in question.lower():
        if character.isalnum():
            cleaned = cleaned + character
        else:
            cleaned = cleaned + " "

    # Drop filler words so the name describes the actual metric.
    keep = []
    for word in cleaned.split():
        if word not in STOP_WORDS:
            keep.append(word)

    keep = keep[:SLUG_MAX_WORDS]

    if not keep:
        return "query"

    return "_".join(keep)


def save_sql(sql, question):
    """Write the query to sql/ and return the path it was written to."""
    os.makedirs(SQL_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SQL_DIR, f"{make_slug(question)}_{timestamp}.sql")

    # A comment header so the file explains itself later on.
    header = f"-- Question: {question}\n-- Generated: {timestamp} by {MODEL}\n\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + sql + "\n")

    return path


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

load_dotenv(encoding="utf-8-sig")

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    sys.exit(1)

# Use the question from the command line if there is one
if len(sys.argv) > 1:
    question = sys.argv[1]
else:
    question = QUESTION.strip()

# Load both metadata files
metric_data = load_json(METRIC_PATH)
dictionary_data = load_json(DICT_PATH)

metrics = metric_data["metrics"]
columns = dictionary_data["columns"]

# Build the context that goes into the prompt
schema_text = build_schema_text(columns)
metric_text = build_metric_text(metrics)
system_prompt = build_system_prompt(schema_text, metric_text)

table_count = len(group_columns_by_table(columns))
print(f"Context: {table_count} tables, {len(columns)} columns, {len(metrics)} metrics")
print(f"Question: {question}\n")

# Ask the model
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

sql = generate_sql(client, question, system_prompt)

# Prompt rules are only a request. These checks read the finished SQL, and
# anything they find is sent back to be corrected.
for attempt in range(1, MAX_FIX_ATTEMPTS + 2):
    problems = hard_problems(sql, GAME_ID)
    if not problems:
        break
    if attempt > MAX_FIX_ATTEMPTS:
        print(f"Still failing after {MAX_FIX_ATTEMPTS} fix attempts.\n")
        break

    print(f"Validation failed, asking for a fix (attempt {attempt}):")
    for name in problems:
        for problem in problems[name]:
            print(f"  [{name}] {problem}")
    print()

    follow_up = question + "\n\n" + build_fix_request(sql, problems)
    sql = generate_sql(client, follow_up, system_prompt)

print(sql)
print()
report(sql, GAME_ID)

saved_path = save_sql(sql, question)
print(f"\nSaved to {saved_path}")
