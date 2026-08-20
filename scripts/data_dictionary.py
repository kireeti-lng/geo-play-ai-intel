import csv
import json
import os
import sys
from collections import defaultdict
from itertools import islice
from dotenv import load_dotenv
from openai import OpenAI

# Load .env first, so the CSV path below can come from it.
load_dotenv(encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# The BigQuery schema export to describe. Set BQ_EXPORT_CSV in .env to point
# somewhere else; the path below is only the fallback.
DEFAULT_CSV = r"C:\Users\KireetiChennuru\Downloads\bquxjob_6900550f_1a014334b92.csv"
CSV_PATH = os.environ.get("BQ_EXPORT_CSV") or DEFAULT_CSV

# Output paths are built from this file's location, not the current folder.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
JSON_OUT = os.path.join(OUTPUT_DIR, "data_dictionary.json")
CSV_OUT = os.path.join(OUTPUT_DIR, "data_dictionary.csv")

MODEL = "openai/gpt-5.2"
BATCH_SIZE = 20
DOMAIN = "a mobile games analytics data warehouse (players, segments ,sessions, ads, A/B tests, and revenue)"

SYSTEM_PROMPT = f"""
Create a data dictionary for {DOMAIN}.
Input format: table_name: col1, col2, ...

Rules:
- Treat each column within its table context.
- Write one concise business description per column.
- Confidence must be 'high', 'medium', or 'low'.
- Return ONLY JSON matching this schema:
{{
  "columns": [
    {{"table_name": "...", "column_name": "...", "description": "...", "confidence": "..."}}
  ]
}}
""".strip()

# ---------------------------------------------------------------------------
# SETUP & DATA INGESTION
# ---------------------------------------------------------------------------
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(CSV_PATH):
    print(f"Missing schema export CSV: {CSV_PATH}")
    print("Set BQ_EXPORT_CSV in your .env file to point at the BigQuery export.")
    sys.exit(1)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

# Read CSV and group columns by table using defaultdict(set) to drop duplicates
table_groups = defaultdict(set)
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        table = row["table_name"].strip()
        column = row["column_name"].strip()
        if table and column:
            table_groups[table].add(column)

# Sort for deterministic processing
table_dict = {tbl: sorted(cols) for tbl, cols in sorted(table_groups.items())}

print(f"Loaded {len(table_dict)} tables and {sum(len(c) for c in table_dict.values())} total columns.\n")

# ---------------------------------------------------------------------------
# LLM PROCESSING (BATCHED)
# ---------------------------------------------------------------------------

# Chunking the Dictionary into smaller batches for processing

def chunk_dict(data, size):
    """Yield successive chunks from a dictionary."""
    it = iter(data.items())
    while chunk := dict(islice(it, size)):
        yield chunk

results = []
table_chunks = list(chunk_dict(table_dict, BATCH_SIZE))


# Preparing the prompt for the LLM

for i, batch in enumerate(table_chunks, start=1):
    user_prompt = "\n".join(f"{table}: {', '.join(cols)}" for table, cols in batch.items())

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        content = json.loads(response.choices[0].message.content)
        batch_columns = content.get("columns", [])
        results.extend(batch_columns)
        print(f"Batch {i}/{len(table_chunks)} completed ({len(batch_columns)} columns described).")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Batch {i} failed to parse: {e}")

# ---------------------------------------------------------------------------
# SAVE OUTPUTS
# ---------------------------------------------------------------------------

# 1. Write JSON
with open(JSON_OUT, "w", encoding="utf-8") as f:
    json.dump(
        {
            "source_file": CSV_PATH,
            "total_columns": len(results),
            "columns": results,
        },
        f,
        indent=2,
        ensure_ascii=False,
    )

# 2. Write CSV
fieldnames = ["table_name", "column_name", "confidence", "description"]
with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(results)

print(f"\nDone! Outputs saved to:\n- {JSON_OUT}\n- {CSV_OUT}")