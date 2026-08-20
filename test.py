from itertools import islice
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -----------------------------
# Configuration
# -----------------------------
MODEL = "openai/gpt-5.2"

DOMAIN = "a mobile games analytics data warehouse (players, segments, sessions, ads, A/B tests, and revenue)"

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

# Connect to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# Which model to use (cheap and good for analysis)
model = "openai/gpt-5.2"

# -----------------------------
# Sample data (Tables & Columns)
# -----------------------------
data = {
    "dim_games": ["id", "game_id", "game_name", "genre"],
    "dim_players": ["player_id", "game_id", "country", "created_at"],
    "fct_sessions": ["session_id", "player_id", "duration_seconds"],
    "fct_revenue": ["transaction_id", "player_id", "amount_usd"]
}


BATCH_SIZE = 2


# -----------------------------
# Chunk dictionary
# -----------------------------
def chunk_dict(data, size):
    """Yield successive chunks from a dictionary."""
    it = iter(data.items())

    while chunk := dict(islice(it, size)):
        yield chunk


# -----------------------------
# Split into batches
# -----------------------------
table_chunks = list(chunk_dict(data, BATCH_SIZE))

print(f"Created {len(table_chunks)} batch(es)\n")

results = []


# -----------------------------
# Process each batch
# -----------------------------
for i, batch in enumerate(table_chunks, start=1):

    user_prompt = "\n".join(
        f"{table}: {', '.join(cols)}"
        for table, cols in batch.items()
    )

    print(f"\nProcessing Batch {i}")
    print(user_prompt)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        # Step 1: Parse the raw JSON string response from the model
        content = json.loads(response.choices[0].message.content)  

        # Step 2: Safely extract the list of column descriptions using .get("columns", [])
        batch_columns = content.get("columns", [])
        
        results.extend(batch_columns)
        print(f"Batch {i}/{len(table_chunks)} completed ({len(batch_columns)} columns described)")

    except (json.JSONDecodeError, KeyError) as e:
        print(f"Batch {i} failed: {e}")


# -----------------------------
# Final result
# -----------------------------
print("\nFinal Results:\n")

for item in results:
    print(
        f"{item['table_name']}."
        f"{item['column_name']} -> "
        f"{item['description']}"
        f"(confidence: {item['confidence']})"
    )

print(f"\nTotal columns processed: {len(results)}")