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

MODEL = "openai/gpt-5.2"
SQL_DIALECT = "BigQuery standard SQL"

# Ask your question here. A question passed on the command line overrides this.
QUESTION = "Show ARPDAU by country for the last 7 days."

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
            tables[table_name] = []
        tables[table_name].append(column)
    return tables


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


def build_metric_text(metrics):
    """Render the metric catalogue as 'name: definition' lines for the prompt."""
    lines = []
    for metric in metrics:
        lines.append(f"{metric['metric_name']}: {metric['definition']}")
    return "\n".join(lines)


def build_system_prompt(schema_text, metric_text):
    """Combine the schema and the metric definitions into the system prompt."""
    return f"""
You are a SQL generator for a mobile games analytics warehouse.
Write one {SQL_DIALECT} query that answers the user's question.

Rules:
- Use only the tables and columns listed under AVAILABLE TABLES. Do not invent names.
- If the question names a metric from METRIC DEFINITIONS, compute it exactly as the
  definition states, using the numerator and denominator it specifies.
- Return only the SQL query. No explanation, no markdown, no code fences.

AVAILABLE TABLES
{schema_text}

METRIC DEFINITIONS
{metric_text}
""".strip()


# ---------------------------------------------------------------------------
# SQL GENERATION
# ---------------------------------------------------------------------------


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


def save_sql(sql, question):
    """Write the query to sql/ and return the path it was written to."""
    os.makedirs(SQL_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SQL_DIR, f"query_{timestamp}.sql")

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

print(sql)

saved_path = save_sql(sql, question)
print(f"\nSaved to {saved_path}")
