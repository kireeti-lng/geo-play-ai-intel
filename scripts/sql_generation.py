"""Dedicated NL-to-SQL agent for downstream dashboard query generation."""

import json
import re

from langchain.agents import create_agent

from geoplay.config import get_llm
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
        self._agent = create_agent(
            model=self._llm,
            tools=[invoke_data_agent],
            system_prompt=build_system_prompt(),
        )

    async def generate_sql(self, nl_query):
        payload = {"messages": [{"role": "user", "content": nl_query}]}
        result = await self._agent.ainvoke(payload)
        text = extract_response_text(result)
        sql = extract_sql(text)
        if not sql:
            raise ValueError("Could not extract SQL query from NL-to-SQL agent response")
        return sql
