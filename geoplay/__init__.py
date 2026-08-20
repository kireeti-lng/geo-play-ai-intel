"""Local stand-in for the production ``geoplay`` package.

Only the two pieces ``scripts/sql_generation.py`` imports are provided here:
``geoplay.config.get_llm`` and ``geoplay.tools.invoke_data_agent``. Keeping the
same module paths means that file's import lines need no changes at all.
"""
