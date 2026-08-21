"""Tool the NL-to-SQL planner calls to learn about the warehouse.

In production this delegates to a SQL agent with live BigQuery access. Here it
returns the project's own metadata instead: the data dictionary (what columns
exist) plus the metric catalogue (what each metric means).
"""

import json
import os

from langchain_core.tools import tool

from geoplay.rules import GAME_ID, SQL_DIALECT, build_reminder, build_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH = os.path.join(REPO_ROOT, "output", "data_dictionary.json")
METRIC_PATH = os.path.join(REPO_ROOT, "metric_catalogue", "metric_catalogue.json")

def load_json(path):
    """Read one JSON file and return it as a dictionary."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_schema_text(columns):
    """Render the data dictionary as compact lines, grouped by table."""
    tables = {}
    for column in columns:
        table_name = column["table_name"]
        if table_name not in tables:
            tables[table_name] = []
        tables[table_name].append(column)

    lines = []
    for table_name in sorted(tables):
        lines.append(f"TABLE {table_name}")
        for column in tables[table_name]:
            lines.append(f"  - {column['column_name']}: {column['description']}")
        lines.append("")
    return "\n".join(lines)


def build_metric_text(metrics):
    """Render the metric catalogue as 'name: definition' lines."""
    lines = []
    for metric in metrics:
        lines.append(f"{metric['metric_name']}: {metric['definition']}")
    return "\n".join(lines)


def build_context():
    """Load both metadata files and return them as one block of text."""
    columns = load_json(DICT_PATH)["columns"]
    metrics = load_json(METRIC_PATH)["metrics"]

    return (
        "AVAILABLE TABLES\n"
        + build_schema_text(columns)
        + "\nMETRIC DEFINITIONS\n"
        + build_metric_text(metrics)
    )


@tool("invoke_data_agent")
async def invoke_data_agent(query: str) -> str:
    """Look up the warehouse schema and metric definitions for a question.

    Args:
        query: The plain-language analytics question being planned.

    Returns:
        The tables and columns that exist, plus the definition of every metric.
    """
    # Order matters twice over.
    #
    # Everything static comes first, so the ~118,000 characters of rules, schema
    # and reminder are byte-identical on every request and can be served from
    # the provider's prompt cache. Interpolating the question at the top - as
    # this did originally - left only 33 characters of shared prefix and made
    # the whole message uncacheable.
    #
    # The question then comes last, where it is freshest, with the reminder just
    # before it so the load-bearing rules stay close to the end too.
    return (
        build_rules()
        + "\n\n"
        + build_context()
        + "\n\n"
        + build_reminder()
        + f"\n\nQuestion being planned: {query}"
    )
