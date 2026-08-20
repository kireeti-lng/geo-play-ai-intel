import csv
import json
import os
from collections import defaultdict

# Paths
CSV_PATH = r"C:\Users\KireetiChennuru\Downloads\bquxjob_6900550f_1a014334b92.csv"
OUTPUT_PATH = r"payload_source\schema.json"

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# Group columns by table
table_groups = defaultdict(list)
with open(CSV_PATH, mode="r", newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        table_name = row["table_name"].strip()
        column_name = row["column_name"].strip()
        data_type = row.get("data_type", "STRING").strip()

        table_groups[table_name].append({
            "column_name": column_name,
            "data_type": data_type
        })

# Build JSON structure
tables = [
    {
        "table_name": tbl,
        "columns": cols
    }
    for tbl, cols in table_groups.items()
]

schema_json = {
    "tables": tables
}

# Write output
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(schema_json, f, indent=2)

print(f"Generated {OUTPUT_PATH} ({len(tables)} tables)")