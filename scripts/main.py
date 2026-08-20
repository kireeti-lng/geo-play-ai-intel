"""Ask a question through OpenRouter.

How to run it:
    python main.py                  -> sends the PROMPT written below
    python main.py "your question"  -> sends that question instead
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# ASK YOUR QUESTION HERE
# Replace the text between the triple quotes. Multiple lines are fine.
# A prompt passed on the command line overrides this.
# ---------------------------------------------------------------------------

PROMPT = """
Reply with exactly: connection ok
"""

# Optional: sets the assistant's role and standing instructions for every run.
# Leave as "" to skip it.
SYSTEM_PROMPT = ""

# ---------------------------------------------------------------------------

# Load the API key from the .env file
load_dotenv(encoding="utf-8-sig")

# Connect to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# Which model to use (cheap and good for analysis)
model = "openai/gpt-5.2"

# Stop the answer from getting too long, so it costs less
max_tokens = 500

# Use the prompt from the command line if there is one, otherwise use PROMPT
if len(sys.argv) > 1:
    prompt = sys.argv[1]
else:
    prompt = PROMPT.strip()

# Build the list of messages to send
messages = []

if SYSTEM_PROMPT != "":
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

messages.append({"role": "user", "content": prompt})

# Send the question and get the answer back
response = client.chat.completions.create(
    model=model,
    messages=messages,
    max_tokens=max_tokens,
)

# Show the result
print("model: ", response.model)
print("reply: ", response.choices[0].message.content)
print("tokens:", response.usage.prompt_tokens, "in /", response.usage.completion_tokens, "out")
