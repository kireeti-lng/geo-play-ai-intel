"""Dedicated NL-to-SQL agent for downstream dashboard query generation."""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime

from langchain.agents import create_agent

# Make the repo root importable so `geoplay` resolves when this file is run
# directly as a script. Appended, not inserted, so a real installed geoplay
# package would still win.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geoplay.config import get_llm
from geoplay.rules import build_rules
from geoplay.tools import invoke_data_agent


def normalize_content(content):
    """Turn a message's content into plain text.

    LangChain messages hold either a string or a list of content blocks,
    so both shapes are handled here.
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()

    return str(content)


def build_system_prompt():
    """The standing instructions given to the planner agent."""
    return (
        "You are an NL-to-SQL planner. "
        "Use only the invoke_data_agent tool. "
        "Ask the tool to 'reason/validate with data, but your final output must be ONLY the final SQL query text "
        "for downstream dashboard execution.' "
        "Do not output explanations, markdown, bullets, or code fences. "
        "Return exactly one SQL query."
    )


def extract_response_text(result):
    """Pull the agent's final text out of whatever shape it returned."""
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]

            # Messages can be objects (LangChain) or plain dictionaries.
            content = getattr(last, "content", None)
            if content is None and isinstance(last, dict):
                content = last.get("content")

            text = normalize_content(content)
            if text:
                return text

        text = normalize_content(result.get("output"))
        if text:
            return text

    return normalize_content(result)


def extract_sql(raw):
    """Find the SQL in the agent's reply and end it with a single semicolon.

    Checked in order: a JSON payload with a "query" field, a ```sql block,
    any other fenced block, then the raw text as-is.
    """
    text = (raw or "").strip()
    if not text:
        return ""

    # 1. A JSON payload such as {"query": "SELECT ..."}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        query = payload.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip().rstrip(";") + ";"

    # 2. A ```sql fenced block (use the last one if there are several)
    sql_blocks = re.findall(r"```sql\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if sql_blocks:
        query = sql_blocks[-1].strip()
        if query:
            return query.rstrip(";") + ";"

    # 3. Any other fenced block
    generic_blocks = re.findall(r"```(?:\w+)?\s*(.*?)```", text, flags=re.DOTALL)
    if generic_blocks:
        query = generic_blocks[-1].strip()
        if query:
            return query.rstrip(";") + ";"

    # 4. Treat the whole reply as the query
    return text.rstrip(";") + ";"


class NLToSQLAgent:
    """Converts natural-language analytics asks into executable SQL."""

    def __init__(self, model=None):
        self._llm = model or get_llm()
        # The production prompt stays verbatim as the prefix; the shared rules
        # are appended so the planner has them from its first turn, rather than
        # only on the second turn behind the schema the tool returns.
        self._agent = create_agent(
            model=self._llm,
            tools=[invoke_data_agent],
            system_prompt=build_system_prompt() + "\n\n" + build_rules(),
        )

    async def generate_sql(self, nl_query):
        payload = {"messages": [{"role": "user", "content": nl_query}]}
        result = await self._agent.ainvoke(payload)
        text = extract_response_text(result)
        sql = extract_sql(text)
        if not sql:
            raise ValueError("Could not extract SQL query from NL-to-SQL agent response")
        return sql


# ---------------------------------------------------------------------------
# COMMAND LINE ENTRY POINT
# ---------------------------------------------------------------------------
# Everything above is the agent library, unchanged. The block below lets the
# file be run directly:
#
#     python scripts/sql_generation.py "What is ARPU for the last 30 days?"

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")

QUESTION = "Show ARPDAU by country for the last 7 days."

# How many times to send failed checks back for correction before giving up.
MAX_FIX_ATTEMPTS = 2

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do", "does",
    "for", "from", "get", "give", "had", "has", "have", "how", "i", "in", "is",
    "it", "many", "me", "much", "my", "of", "on", "or", "our", "over", "per",
    "show", "tell", "that", "the", "their", "there", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "with",
}
SLUG_MAX_WORDS = 8


def make_slug(question):
    """Turn a question into a short, readable filename part."""
    cleaned = ""
    for character in question.lower():
        if character.isalnum():
            cleaned = cleaned + character
        else:
            cleaned = cleaned + " "

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

    header = f"-- Question: {question}\n-- Generated: {timestamp} by the NL-to-SQL agent\n\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + sql + "\n")

    return path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = sys.argv[1]
    else:
        question = QUESTION

    print(f"Question: {question}\n")

    started = time.time()
    agent = NLToSQLAgent()
    sql = asyncio.run(agent.generate_sql(question))

    # Prompt rules are only a request. These checks read the finished SQL, and
    # anything they find is sent back to be corrected.
    from geoplay.rules import GAME_ID
    from geoplay.telemetry import record
    from geoplay.validate import build_fix_request, hard_problems, report, validate

    retries_used = 0
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
        sql = asyncio.run(agent.generate_sql(follow_up))
        retries_used = attempt

    print(sql)
    print()
    report(sql, GAME_ID)

    record(
        question=question,
        sql=sql,
        model=agent._llm.model_name,
        problems=validate(sql, GAME_ID),
        retries=retries_used,
        seconds=round(time.time() - started, 1),
        generator="agent",
    )

    print(f"\nSaved to {save_sql(sql, question)}")
