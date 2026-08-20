# NL→SQL Simplification — Implementation Plan and Record

Status: **complete**. Written 2026-08-20.

---

## 1. Context, and a correction to the original brief

The task was framed as *simplifying an existing implementation* that loads `metric_catalogue.json` and
`data_dictionary.json`, builds context, and generates SQL.

**No such file existed.** Three findings, each verified before any code was written:

1. **`scripts/sql_generation.py` was a byte-identical copy of production code from another repo** —
   `C:\geoplay\geo-play-intel\geo-play-intel\src\geoplay\agents\nl_to_sql_agent.py` (110 lines, same
   docstring, `md5 123ba41e…`). It references **neither** JSON file; its context arrives at runtime through
   `invoke_data_agent`, a tool that lives in that other repo. It could not even be imported here — `langchain`
   is not installed and the `geoplay` package does not exist in this repo. It was orphaned reference code, not
   working production code.

2. **`data_dictionary_v2.py` (repo root) is byte-identical to `scripts/data_dictionary.py`** (`diff` reports no
   difference). It is a data-dictionary *generator*: it **writes** `output/data_dictionary.json` from a
   BigQuery CSV export. It never reads the metric catalogue and never generates SQL.

3. Therefore the flow `User Request → load both JSONs → build context → generate SQL` had to be **written**,
   not refactored.

What `data_dictionary_v2.py` did provide is the one LLM-call pattern **proven to run in this environment**:
the `openai` SDK pointed at OpenRouter, `load_dotenv(encoding="utf-8-sig")`, `OPENROUTER_API_KEY`, model
`openai/gpt-5.6-luna`. Phase 1 adopts that pattern deliberately.

### Decisions taken

| Decision | Choice |
|---|---|
| Phase 1 | New script in `data_dictionary_v2.py`'s flat OpenRouter style — not a refactor of v2 itself |
| Phase 2 | Simplify `scripts/sql_generation.py` in place; ~~static validation only, no new dependencies~~ — **superseded, see §7: it is now a working main file** |
| Context strategy | Compact-render everything; no keyword filtering |

---

## 2. Phase 1 — `scripts/sql_generation_simple.py` (new)

### Execution flow

```
argv[1] or QUESTION
        │
        ├── load_json(METRIC_PATH)  →  metric_catalogue.json   →  49 metrics
        ├── load_json(DICT_PATH)    →  data_dictionary.json    →  948 columns / 50 tables
        │
        ├── build_schema_text()  → "TABLE x" + "  - col: description" lines
        ├── build_metric_text()  → "Metric Name: definition" lines
        ├── build_system_prompt() → dialect + rules + AVAILABLE TABLES + METRIC DEFINITIONS
        │
        ├── generate_sql()  → one OpenRouter chat call (system = context, user = question)
        ├── clean_sql()     → strip ``` fences, normalize to a single trailing ";"
        ├── print(sql)
        └── save_sql()      → sql/query_<YYYYMMDD_HHMMSS>.sql
```

### Output files

Every run writes one timestamped file to `sql/` (the directory is created on first run), and also prints to
stdout so the script stays usable in a pipe. Each file opens with a two-line `--` comment header recording the
question, the timestamp, and the model, so an archived query explains itself months later; `--` comments are
valid SQL, so the file remains directly executable.

One file per run means no query is ever silently overwritten. If downstream tooling needs a predictable path
instead, adding a fixed `sql/latest.sql` alongside the timestamped file is a two-line change to `save_sql()`.

### How the two JSON files are used

**`data_dictionary.json`** supplies the *schema*. Its flat `columns` list — each row
`{table_name, column_name, description, confidence}` — is grouped by table and rendered as compact lines. This
is what stops the model inventing table and column names.

**`metric_catalogue.json`** supplies the *semantics*. Each row `{metric_id, metric_name, definition}` becomes
a `name: definition` line. This is the load-bearing half: the definitions state numerator and denominator
explicitly, which is precisely what a schema listing cannot convey.

That the catalogue genuinely reaches the model is demonstrable, not assumed. Asked for *"ARPDAU by country for
the last 7 days"*, the model produced a per-day aggregate wrapped in an outer `AVG(...)` — the arithmetic mean
of daily values. That is exactly what the ARPDAU definition prescribes ("Multi-day figures are conventionally
computed as the arithmetic mean of daily values rather than as period revenue over period unique users"), and
it is *not* the naive reading a bare schema would suggest.

### Measured context budget

| Block | Chars | ~Tokens |
|---|---|---|
| Schema (50 tables, 948 columns) | 88,914 | ~22,200 |
| Metrics (49 definitions) | 20,324 | ~5,100 |
| **Combined** | **109,238** | **~27,300** |

Roughly half of what the raw JSON (~57k tokens) would cost.

### Design notes

- Paths anchor to `__file__`, **not** the process CWD, so the script runs from any directory. Every sibling
  generator assumes repo-root CWD, which is the most likely runtime trip-up.
- Plain module-level functions; no classes, no generators, no walrus operator, no nested comprehensions, no
  `try/except`. Two simple `if` guards cover the only things that actually fail in practice: a missing API key
  and a missing JSON file.
- `clean_sql` is deliberately simpler than the production three-tier extractor. The JSON-`query` tier exists
  in production because its upstream *tool* can return JSON; a direct chat call cannot, so that tier would be
  dead code here.

---

## 3. Phase 2 — `scripts/sql_generation.py` (simplified in place)

### Preserved exactly

Public surface, because production callers import it: class `NLToSQLAgent`, `__init__(self, model=None)`,
`async def generate_sql(self, nl_query)`, the `ValueError("Could not extract SQL query from NL-to-SQL agent
response")`, and the system prompt **character-identical** (300 chars).

Extraction precedence unchanged: JSON `query` field → **last** ```sql fence → **last** generic fence → raw
text; every branch returning `.rstrip(";") + ";"`.

### Changes made

| Advanced construct | Simplified to |
|---|---|
| `from __future__ import annotations` | removed — Python here is 3.12.4, so it was a no-op |
| `from typing import Any, Optional` + annotations | removed; plain untyped parameters |
| `_normalize_content` isinstance ladder | same branches, plain `for` loop, named locals, docstring |
| `@staticmethod _build_system_prompt` / `_extract_sql` | module-level `build_system_prompt()` / `extract_sql()` |
| `_extract_response_text` method | module-level `extract_response_text()` |
| `except Exception: pass` around `json.loads` | narrowed to `except json.JSONDecodeError` |
| numbered comments on the four extraction tiers | added |
| `getattr(last, "content", None)` fallback | **kept** — LangChain returns message objects, not dicts |

The class stays. It is the genuine public API, not an over-abstraction.

File went 110 → 133 lines. The growth is docstrings and comments; the mechanical de-indentation from moving
static methods to module level is why the raw diff touches most lines despite the logic being provably
unchanged.

### Validation — differential test

Static validation cannot exercise the real LLM, but it can prove behavior is unchanged. Throwaway
`langchain` / `geoplay` stubs were written **in the scratchpad only** — nothing added to the repo or to
`requirements.txt` — and the pre-refactor snapshot was compared against the refactored file case by case:

- **20** `extract_sql` cases: bare SQL, semicolon variants, JSON `query`, non-dict JSON payloads, `sql` fence,
  uppercase fence, two fences (last wins), generic fence, fence precedence, empty fence, empty/whitespace/None.
- **11** `normalize_content` cases: string, `None`, block lists, missing `text` keys, mixed lists, non-string.
- **11** `extract_response_text` cases: plain string, dict messages, LangChain-style message objects, `output`
  fallback, empty dict, `None`.
- **10** surface/prompt/wiring checks: class name, docstrings, signatures, defaults, async-ness, prompt string.
- **5** full `async generate_sql` end-to-end cases through the stub agent.

**57 checks, 0 divergences.**

---

## 4. Dependencies and configuration

- `requirements.txt` (`openai>=1.0`, `python-dotenv>=1.0`) **already covered Phase 1** — no edit was needed.
  Phase 1 imports only `json`, `os`, `sys` (stdlib) plus `dotenv` and `openai`.
- `langchain` is a dependency of the *other* repo and was deliberately **not** added here.
- Env: `OPENROUTER_API_KEY` (required). `OPENROUTER_MODEL` exists in `.env`, but every sibling script hardcodes
  `MODEL`; Phase 1 follows that convention.

---

## 5. Phase 1 vs Phase 2

| | Phase 1 — `sql_generation_simple.py` | Phase 2 — `sql_generation.py` |
|---|---|---|
| Origin | New, written here | Copy of another repo's production file |
| Context source | Reads both JSON files directly | `invoke_data_agent` tool at runtime |
| LLM access | `openai` SDK → OpenRouter | LangChain agent via `get_llm()` |
| Style | Flat functions, sync, CLI entry point | Class, async, library entry point |
| Runs in this repo | **Yes**, verified end to end | **No** — deps absent by design |
| Metric catalogue used | Yes, in the system prompt | No |

**Which is safer as the production implementation?** Neither, as they stand — and they are not competing for
the same slot. Phase 2's file is a *read-only copy*; edits here never reach production, whose real home is
`src/geoplay/agents/nl_to_sql_agent.py` in the other repo. Its value is as a reviewed patch to port over.
Phase 1 is a working local tool, but it is a single-shot generator with no validation, no dry-run, and no
execution against a warehouse — fine for drafting and inspection, not for serving a dashboard unattended.

The genuinely useful synthesis: Phase 1 proves the metric catalogue measurably improves SQL correctness by
pinning denominators. Feeding that same catalogue into the production agent's context is the change worth
making next.

---

## 6. Assumptions and known limits

- **BigQuery dialect** was inferred from the `bquxjob_*` source CSV filename, not from any config. If the
  warehouse differs, one constant (`SQL_DIALECT`) changes.
- **Phase 2's real LLM/agent path was never executed** — no langchain, no geoplay package. The pure helpers,
  the import graph, and the async method were proven against stubs. This is not the same as "runs in
  production" and should not be reported as such.
- **Generated SQL was never executed** against a warehouse; no credentials or connection exist here. Column
  and table names were checked to exist in the data dictionary; query *semantics* were reviewed by reading.
- **Pre-existing quirk preserved, not fixed:** when the agent returns a message whose content is empty,
  `extract_response_text` falls through and stringifies the whole result dict, so `extract_sql` returns that
  string and the `ValueError` never fires. Confirmed present in the original. Left as-is because Phase 2 is
  behavior-preserving; worth raising separately against the production repo.
- **`data_dictionary_v2.py` and `scripts/data_dictionary.py` are duplicate files.** Out of scope here, but a
  real maintenance hazard — edits to one will silently diverge from the other.

---

## 7. Phase 2 revised — `sql_generation.py` as a working main file

The original Phase 2 decision was *simplify only, static validation, no new dependencies*. That was
superseded: the file is now expected to **run**, with minimal changes to the file itself.

### What was added

| Item | Where | Why |
|---|---|---|
| `langchain>=1.3,<2`, `langchain-openai>=1.6,<2` | `requirements.txt` | `create_agent` and `ChatOpenAI` |
| `geoplay/__init__.py`, `config.py`, `tools.py` | **new package** | Supplies the two imports the file already had |
| `sys.path.append(repo_root)` | 3 lines near the imports | So `geoplay` resolves when run as a script |
| CLI entry point + `make_slug` / `save_sql` | appended below the class | Makes it runnable and archives output to `sql/` |

The agent class itself is **untouched**. `create_agent` in langchain 1.3.15 takes exactly
`(model, tools, system_prompt)` — the signature the production code already called — so `__init__`
needed no edit at all. File went 133 → 214 lines, all of it appended below the class or added to the
import block.

### The local `geoplay` package

Same module paths as production, so the import lines stay byte-identical:

- **`geoplay.config.get_llm(model_name=None)`** — returns `ChatOpenAI` over OpenRouter,
  `temperature=0.1`, model from `OPENROUTER_MODEL` then `openai/gpt-5.2`. Mirrors production's
  `config/runtime.py` minus its internal metering callback.
- **`geoplay.tools.invoke_data_agent(query)`** — a `@tool`-decorated async function. Production
  delegates to a BigQuery-backed SQL agent; here it returns this project's own metadata instead:
  the compact schema (50 tables / 948 columns) plus all 49 metric definitions, 109,325 characters.

That second point is the interesting one. **The production agent has no access to the metric
catalogue** — its tool returns query results, not definitions. Wiring the catalogue into the tool
response is the change worth porting upstream.

### A real defect this surfaced

The first successful run emitted `DATEADD(day, -29, CURRENT_DATE())` — SQL Server / Snowflake
syntax, invalid on BigQuery. Cause: the production system prompt **names no SQL dialect** (verified —
no occurrence of "bigquery", "dialect", or "standard sql" in its 300 characters). In production that
is survivable because the real tool delegates to a dialect-aware agent; with a metadata-only tool,
nothing states the target dialect.

Fixed in the **shim**, not the production prompt — `geoplay/tools.py` declares
`SQL_DIALECT = "BigQuery standard SQL"` and states it in the tool response. This keeps the prompt
character-identical (preserving the §3 guarantee) while correcting the output. The tool is the right
home for it: knowing which warehouse the metadata describes is the tool's job. After the fix the
same question produced `DATE_SUB(CURRENT_DATE(), INTERVAL 29 DAY)` and `SAFE_DIVIDE`.

### Validation

| Check | Result |
|---|---|
| `from langchain.agents import create_agent` | imports; accepts `model` / `tools` / `system_prompt` |
| `NLToSQLAgent()` constructs | `ChatOpenAI(openai/gpt-5.2)` + `CompiledStateGraph` |
| Behavioural helpers vs pre-refactor original | 50 differential checks, 0 divergences |
| Wiring vs original (by config, not identity) | 4 checks — llm config, agent type, prompt all identical |
| System prompt | 300 chars, character-identical |
| End-to-end run | SQL generated, printed, saved to `sql/` |
| Generated SQL grounded | 1 real table, 1 CTE, all 6 columns exist in `fact_user_daily` |
| Dialect correct after fix | `DATE_SUB` / `SAFE_DIVIDE`, no `DATEADD` |

### Two files, two roles

| | `sql_generation_simple.py` | `sql_generation.py` |
|---|---|---|
| Architecture | One direct chat call | LangChain agent + tool loop |
| Context delivery | Injected in the system prompt | Fetched by the agent calling a tool |
| API calls per question | 1 | 2+ (planner turn, tool turn, answer turn) |
| Dependencies | `openai`, `python-dotenv` | those + `langchain`, `langchain-openai`, `langgraph` |
| Matches production | no | yes — same class, prompt, tool interface |

Both now work and both save to `sql/`. The simple one is cheaper and easier to debug; the agent one
is the shape production actually runs, so it is the one to test changes against before porting them.

### Still true

- **Generated SQL is never executed.** No warehouse connection exists. Column and table names are
  checked against the data dictionary; semantics are reviewed by reading.
- **The empty-content bug from §3 is still preserved,** not fixed — behaviour-preserving was the goal.
- **`run_pipeline.py` still calls `sql_generation_simple.py` for stage 3.** Switching it to the agent
  version is a one-line change, deliberately not made without asking.
