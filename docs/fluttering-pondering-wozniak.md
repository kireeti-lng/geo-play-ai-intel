# Grounded NL→SQL generator for geo-play-ai-intel

## Context

`sql_generation.py` in this repo is a **byte-identical copy** of `geoplay/agents/nl_to_sql_agent.py`
from `C:\geoplay\geo-play-intel\geo-play-intel` (verified with `diff` — no output). It imports
`langchain.agents.create_agent`, `geoplay.config.get_llm`, and `geoplay.tools.invoke_data_agent`.
None of those exist here — this repo's `requirements.txt` is only `openai>=1.0` and
`python-dotenv>=1.0`. **The file cannot run in this repo at all.**

What it does contain is a 5-line system prompt, langchain response unwrapping, and a fenced-code
extractor whose final fallback returns arbitrary prose as if it were SQL. It has no schema context,
no metric awareness, and no validation.

Meanwhile this repo already holds the two things a grounded generator needs:
`output/data_dictionary.json` (948 columns across 50 tables, produced by `data_dictionary.py`) and
`payload_source/schema.json` (the authoritative table list plus every `data_type`). The missing
half is metric semantics — *what DAU means, and how it is legally aggregated*.

The goal: a standalone, sync, OpenRouter-based generator that turns a natural-language analytics
question into governed BigQuery SQL grounded in the data dictionary **and** a metric catalogue,
validates it against the dictionary without touching a warehouse, and reports honestly how much
it trusts the result. SQL is generated, never executed.

### Decisions taken (confirmed with the user)

| | Decision |
|---|---|
| Rewrite shape | Standalone **sync** `openai` client. No langchain, no `geoplay` imports, no BigQuery client, no async. |
| Metric catalogue | **The user supplies `metric_catalog.json`.** This plan does not generate it — it publishes a contract and an offline auditor. |
| Validation | **Add `sqlglot`** to `requirements.txt`, with a regex fallback so the code still runs without it. |
| html-doc skill | Lives in **this repo** at `.claude/skills/html-doc/`. The separate `kireeti_claude_code` project folder is dropped per the user's redirect. |

---

## Task 2 answer: how much already exists

Assessed against the 16 components a dictionary-and-catalogue-grounded SQL generator needs.
"Portable" = missing here, but working code exists in `geo-play-intel` to copy from.

| # | Component | State in `sql_generation.py` |
|---|---|---|
| 1 | LLM client + config plumbing | **Present** (via `get_llm`; also already solved locally in `data_dictionary.py`) |
| 2 | Response-text normalization | **Present** — but only needed because of langchain; worthless once sync |
| 3 | SQL extraction from JSON / fences | **Present** — the one genuinely reusable idea |
| 4 | System prompt scaffold | **Partial** — 5 lines, no schema, no rules, no dialect |
| 5 | Load `data_dictionary.json` | Missing |
| 6 | Load metric catalogue | Missing (file does not exist yet) |
| 7 | Render dictionary + catalogue into the prompt | Missing |
| 8 | Table/metric shortlisting under a context budget | Missing |
| 9 | Metric-aware SQL semantics (additivity, `COUNT(DISTINCT)`, `SAFE_DIVIDE`) | Missing here — **portable** from `retriever/sources/bigquery_source.py:435-553` (dead code there) |
| 10 | Dialect + target qualification | Missing |
| 11 | Read-only / single-statement enforcement | Missing here — **portable** from `storage/bigquery_store.py:109-140` |
| 12 | Column-existence validation vs the dictionary | Missing here — **portable** from `bigquery_source.py:20-80` (with a known flaw, see §4) |
| 13 | Repair/retry loop on validation failure | Missing |
| 14 | Structured output envelope | Missing — returns a bare `str` |
| 15 | CLI entrypoint | Missing |
| 16 | Evaluation harness | Missing |

**Present: 3 of 16 components, plus 1 partial → ~15–20% by effort, and it is the cheapest 20%**
(client setup and string scraping). **~80–85% is missing.** Weighted by risk rather than lines the
gap is wider: every component that decides whether the SQL is *correct* — grounding, metric
semantics, validation, repair — is absent.

Three specific defects in the existing file, worth naming because they are actively harmful:

1. `_extract_sql`'s final fall-through, `return text.rstrip(";") + ";"`, hands back an apology or an
   explanation as if it were SQL. In `geo-play-intel` this is served from `POST /nl_to_sql` with a
   **200**.
2. Generating SQL through `invoke_data_agent` **executes it against BigQuery** as a side effect,
   possibly several times (the sub-agent self-retries). Expensive for an endpoint whose only job is
   to hand SQL to a dashboard.
3. The sub-agent it calls is prompted for prose and ```` ```render_chart ```` blocks. Getting bare
   SQL out of it works only because an inline instruction asks it to override its own prompt.

---

## Task 3 answer: architecture of the use case

Five stages. Stages 1–2 are already built and were run to produce the artifacts on disk.

```
STAGE 1  SCHEMA HARVEST         BigQuery INFORMATION_SCHEMA -> CSV export
  built    json_schema_generator.py   -> payload_source/schema.json
                                         50 tables / 948 columns / every data_type

STAGE 2  COLUMN SEMANTICS       schema.json -> OpenRouter (openai/gpt-5.3, temp 0.1,
  built    data_dictionary.py            batches of 10 tables, json_object mode)
                                      -> output/data_dictionary.json
                                         948 descriptions, confidence high 848 / med 98 / low 2

STAGE 3  METRIC SEMANTICS       *** USER-SUPPLIED ***
  yours    output/metric_catalog.json  governed metric definitions:
                                       formula, aggregation_type, source_tables, caveats
           validate_metric_catalogue.py  <- offline auditor this plan adds

STAGE 4  GROUNDED GENERATION    question -> shortlist -> generate -> validate -> repair
  build    sql_knowledge.py   joins all three artifacts, indexes them, shortlists
           sql_prompts.py     system prompt R1-R12 + block renderers
           sql_validation.py  sqlglot AST critic, never executes
           sql_generation.py  SqlGenerator + repair loop + argparse CLI

STAGE 5  CONSUMPTION            GeneratedSql envelope -> dashboard / notebook / eval
  build    eval_sql_generation.py + eval/golden_questions.json
```

Trust boundaries worth naming: the **only** network egress is OpenRouter. There is no BigQuery
credential anywhere in this repo and no SQL execution, so a hallucinated `DROP` is a validation
finding, not an incident. Every grounding fact is read from local disk.

Runtime cost per question: **1 router call + 1 generation call + ≤2 repair calls**, ~10–14k prompt
tokens. Rendering all 948 dictionary rows and all metrics into every prompt instead would be ~40k
tokens *per attempt*; §3 explains how shortlisting avoids that.

---

## 1. Files

Flat modules, no package, matching the repo's existing style. Four classes total.

| File | Status | Owns |
|---|---|---|
| `sql_knowledge.py` | new | `Column`/`Table`/`Metric` dataclasses, `KnowledgeBase`, `Shortlister`, `SYNONYM_MAP` |
| `sql_prompts.py` | new | `SYSTEM_PROMPT` (rules R1–R12), `ROUTER_SYSTEM_PROMPT`, block renderers |
| `sql_validation.py` | new | `ValidationIssue`, `ValidationReport`, `SqlValidator` |
| `sql_generation.py` | **rewrite** | `extract_sql`, `GeneratedSql`, `SqlGenerator`, repair loop, CLI |
| `validate_metric_catalogue.py` | new | offline audit of the user's catalogue against the contract |
| `eval/golden_questions.json` | new | ~20 golden cases, one per rule |
| `eval_sql_generation.py` | new | harness; asserts without executing SQL |
| `requirements.txt` | edit | `+ sqlglot` |
| `.claude/skills/html-doc/` | new | `SKILL.md` + `scripts/verify_html.py` (from the .skill zip) |
| `nl_to_sql_architecture.html` | new | Task 4 deliverable (repo root, beside `concepts.html`) |

Untouched: `json_schema_generator.py`, `data_dictionary.py`, `main.py`, `test.py`.

**"Intermediate level Python" means, concretely:** type hints, frozen `dataclasses`, `pathlib`,
module-level constants, small focused functions, comprehensions and generators. **Not** async, ABCs,
`Protocol`, metaclasses, or DI. Sync throughout. `try/except` only where a caller genuinely needs a
degraded path (missing `sqlglot`, malformed model JSON) — not as flow control.

---

## 2. The metric catalogue contract (for the user's file)

The loader looks for `output/metric_catalog.json`, then `output/metric_catalogue.json`. Preferred
shape mirrors `data_dictionary.json`'s envelope so the repo reads consistently:

```json
{
  "domain": "GeoPlay Agentic AI Mobile Gaming Analytics",
  "total_metrics": 164,
  "metrics": [
    {
      "metric_id": "dau",
      "metric_name": "Daily Active Users",
      "aggregation_type": "distinct",
      "definition": "Unique active users per day",
      "numerator_definition": "Unique user_id",
      "denominator_definition": "",
      "source_tables": ["fact_user_activity_daily"],
      "metric_category": "engagement",
      "unit": "count",
      "tier": "L1",
      "time_grain": "Day",
      "filters_applied": "Exclude test users",
      "eligibility_criteria": "Valid sessions only",
      "known_caveats": "Offline caching delays",
      "observability_status": "live",
      "concept_key": "dau",
      "is_higher_better": true,
      "aggregation_provenance": "declared"
    }
  ]
}
```

- **Required:** `metric_id` (unique), `metric_name`, `definition`, `aggregation_type`.
- **`aggregation_type` enum:** `sum` | `distinct` | `ratio` | `cohort` | `unknown`. This single field
  drives rules R4/R5/R6, the additivity validator, and the confidence score — it matters more than
  anything else in the file. **Empty or unrecognised is treated as `unknown`, and `unknown` is
  treated as non-additive** (fail-safe: over-caution, never a wrong number).
- **Required when `aggregation_type` is `ratio` or `cohort`:** `numerator_definition` and
  `denominator_definition`, so R6 can emit `SAFE_DIVIDE(SUM(num), SUM(den))`.
- **Strongly recommended:** `source_tables` naming tables that exist in `schema.json`.
- **Optional but used:** `aggregation_provenance` (`declared`/`inferred`/`unknown`) — rendered into
  the prompt as `(inferred)` so the model knows how far to trust the classification, and it caps
  reported confidence at `medium`.

The loader is **tolerant**: accepts a bare top-level list as well as `{"metrics": [...]}`, and
accepts the aliases `numerator`/`numerator_definition`, `category`/`metric_category`,
`aggregation`/`aggregation_type`, and `source_tables` as either a list or a comma/semicolon string.

`validate_metric_catalogue.py` (no LLM, no network) reports: total metrics, duplicate `metric_id`s,
per-metric missing required fields, `aggregation_type` values outside the enum, the count falling
back to `unknown`, `source_tables` entries absent from `schema.json`, and metrics with no resolvable
table. Run it before the first generation.

> **If a different shape is already fixed on the user's side**, that is a loader-mapping change in
> `KnowledgeBase.load` only — nothing downstream moves.

### Two constraints the source data imposes (verified this session)

Checked directly against `seeds/seed_metric_catalog.csv` in
`C:\geoplay\geo-play-updated-pipelines\geo-play-data-transformations-main`, the likely upstream:

1. **`aggregation_type` is mostly absent.** 190 rows; only **47** declare it (23 `ratio`,
   11 `cohort`, 9 `sum`, 4 `distinct`). 143 are empty. The file is also a union of two disjoint
   vintages — 140 rows keyed `M001`…`M140` carry the prose formulas but no `aggregation_type`;
   50 snake-case rows carry `aggregation_type`/`tier`/`unit` but no prose. There are 160 distinct
   `concept_key`s and **26 clean cross-vintage pairs** (merging those yields 164 entries); `revenue`
   has 3 rows and `versionadoption` has 3 (three real app versions — must **not** be merged).
2. **The metric→table bridge is broken.** `source_tables` says the literal `"Aggregated marts"` on
   126 of 190 rows; only **6** name a table that exists in `schema.json`. `source_tables_applied` is
   better at **65**, still under half. **Consequence: table shortlisting must stand on its own
   against the data dictionary. Metric-driven table inclusion is additive, never the mechanism.**
   A design that assumes `metric.source_tables` resolves will pass on the curated metrics and fail
   on everything else.

---

## 3. Shortlisting: hybrid, router-primary, **table granularity only**

No column-level retrieval. Route over 50 tables, then render *all* columns of the ≤6 chosen tables
— typically ~120 rows ≈ 3k tokens. That alone dissolves the 40k-token problem.

**Why an LLM router and not keyword scoring.** Measured against all 948 dictionary rows and the
full metric list:

| term | hits in metrics | hits in dictionary (name + description) |
|---|---|---|
| `whale` | **0** | **0** |
| `stickiness` | 2 | **0** |
| `churn` | 1 | 2 |
| `dolphin` / `lapsed` | 0 | 0 |

"Who are our whales" has **zero lexical anchor anywhere in the corpus**. No BM25 tuning fixes a term
that appears in neither the metric names nor the ~69k characters of column descriptions. The right
answer (`fact_user_segment_daily.monetization_segment_id` joined to `dim_segment`, or
`spend_usd_to_date`) is reachable only via world knowledge that whales are high spenders.

**Why it's affordable.** At table granularity the router sees the *whole* corpus compacted to
one-liners — 50 tables + the metric list ≈ 5–6k tokens, one call. No embeddings, no index build,
nothing to keep in sync.

**Why keep keywords anyway.** As a **floor**, not a ranker. If the question literally contains
`arppu` or `fact_purchases`, that is force-included even if the router omitted it. Union, never
intersection — and it makes `--no-router` a working, degraded, offline mode.

`SYNONYM_MAP` (~30 hand-written entries, one module constant, reviewable in a minute) feeds **both**
passes: matched entries force tables in *and* are injected into the router prompt as `GLOSSARY HINTS`
so the router learns *why*.

```
1  terms = tokenize(question) | expand(SYNONYM_MAP)
2  forced_tables, forced_metrics = keyword match on table names, metric_ids,
                                   metric_names, concept_keys, column names
3  router call -> {"tables": [...], "metrics": [...], "notes": "..."}   (json_object)
4  tables = router.tables | forced_tables, then closure: add each selected
   metric's source_tables (only those that resolve to real tables)
5  drop unknown names; cap at max_tables=6 / max_metrics=8 (router order first)
6  dedupe metrics sharing a concept_key: prefer is_canonical, else declared provenance
```

---

## 4. Prompts

**System message — static, one constant, identical every call.** Role; BigQuery dialect
(`FLOAT64`/`INT64`/`BOOL` — never `FLOAT`/`INT`/`BOOLEAN`; `DATE_SUB(CURRENT_DATE(), INTERVAL n DAY)`;
`CAST(ts AS DATE)` before comparing a TIMESTAMP to a DATE; `ROWS BETWEEN` not `RANGE`; no window
function in `HAVING`); then twelve numbered hard rules, each phrased as imperative + the failure it
prevents + the correct alternative:

- **R1 READ_ONLY** — exactly one `SELECT` or `WITH…SELECT`. No DML/DDL, no multiple statements, no
  trailing semicolon.
- **R2 COLUMNS_EXIST** — only columns listed under the table they belong to. A column in table A does
  not exist in table B unless listed there too. Never invent or abbreviate.
- **R3 METRIC_DEFINITION_IS_AUTHORITY** — implement a matched metric from its own
  `numerator_definition`/`denominator_definition`/`filters_applied`/`eligibility_criteria` verbatim,
  not from your own idea of the formula. Where provenance shows `(inferred)`, treat the
  classification as provisional and prefer the more conservative aggregation.
- **R4 NO_SUM_OF_NON_ADDITIVE** — only `aggregation_type: sum` may be `SUM`med across time. Never
  `SUM` a `ratio`, `distinct`, `cohort`, or `unknown`. Named offenders: DAU, WAU, MAU, retention
  rates, ARPU, ARPPU, ARPDAU, conversion rates.
- **R5 DISTINCT_MEANS_COUNT_DISTINCT** — `distinct` over a multi-day window is
  `COUNT(DISTINCT user_id)` over that window from a user-grain table, or `HLL_COUNT.MERGE(hll_sketch)`
  from `fact_metrics_daily`/`mart_metrics`/`agg_metrics_periodic`. Never a sum or average of dailies,
  never DAU × a multiplier.
- **R6 RATIOS_ROLL_UP_BY_PARTS** — roll a `ratio` across days as
  `SAFE_DIVIDE(SUM(numerator), SUM(denominator))`. `AVG(value)` is an unweighted mean of daily ratios
  and is a *different number*. Use `AVG` only when the user explicitly asks for an average of dailies.
- **R7 NO_KPI_FROM_KPI** — never derive one KPI from another's stored value: no MAU from DAU, no WAU
  from DAU, no LTV from ARPU, no retention from DAU deltas.
- **R8 SAFE_DIVIDE** — every division uses `SAFE_DIVIDE(a, b)`. Bare `/` only when the divisor is a
  non-zero literal.
- **R9 GRAIN** — respect each table's grain; aggregate before joining where a join would fan out;
  state the result grain.
- **R10 NO_DATE_UNLESS_ASKED** — no date column in `SELECT`/`GROUP BY` unless a trend, time series,
  or per-day breakdown was requested.
- **R11 LONG_NARROW_METRIC_TABLES** — `fact_metrics_daily`, `mart_metrics`, `mart_metrics_cohort`,
  `agg_metrics_periodic` are one row per (date, `metric_id`, dimensions). Always filter
  `metric_id = '<id>'`. Their `value`/`observed_value` is whatever that metric is, so R4–R6 apply
  to it.
- **R12 REFUSE_RATHER_THAN_ESTIMATE** — if the shortlisted tables cannot answer accurately, return
  `unsupported_reason` and no SQL. Never emit proxy logic for a business-critical KPI.

> R6 and R11 are **not** in the `geo-play-intel` prompt being ported — that prompt says to aggregate
> daily metrics with `AVG`, which is wrong for this warehouse. `fact_metrics_daily`, `mart_metrics`,
> `mart_metrics_cohort`, and `agg_metrics_periodic` all carry `numerator`, `denominator`, **and**
> `hll_sketch BYTES`, so both the weighted-ratio and the pre-aggregated-distinct paths exist here.
> Also do **not** carry over its "prefer BOOLEAN" line — this schema uses `BOOL`.

**Output contract**, via `response_format={"type": "json_object"}` (already proven against this model
in `data_dictionary.py`):

```json
{"sql": "...", "metrics_used": ["dau"], "assumptions": ["..."],
 "grain": "one row per day", "explanation": "...", "unsupported_reason": null}
```

**User message — dynamic:** `QUESTION`, `ROUTER NOTES`, `SHORTLISTED METRICS`, `AVAILABLE TABLES AND
COLUMNS`, and on repair only `PREVIOUS ATTEMPT` + `VALIDATION ERRORS`.

Table block — `f"  {name:<26}{dtype:<10}{description[:120]}"`:

```
TABLE fact_user_activity_daily  (9 columns)
  user_id                   STRING    Unique identifier for the registered player.
  event_date                DATE      Calendar date of the daily activity roll-up.
  session_count             INT64     Number of sessions the player started that day.
```

Metric block — empty lines omitted, so there is no wall of `-`:

```
METRIC dau  "Daily Active Users"  [engagement | tier L1 | unit count | live]
  aggregation_type : distinct  (declared)
  definition       : Unique active users per day
  numerator        : Unique user_id
  source_tables    : fact_user_activity_daily
  filters          : Exclude test users
  caveats          : Offline caching delays
```

---

## 5. Validation — six checks, nothing executed

No warehouse, no BigQuery client, no dry-run.

| Check | Rule | Mechanism | Severity | Reliability |
|---|---|---|---|---|
| Read-only | R1 | `sqlglot.parse(read="bigquery")`; every statement `exp.Select`/`Union`/`Subquery`. **Fails closed** — unparseable or empty is an error. | error | **reliable** |
| Single statement | R1 | one non-empty parsed statement | error | **reliable** |
| Unknown table | R2 | `find_all(exp.Table)` minus CTE names, vs `kb.all_table_names()` | error | **reliable** |
| Unknown column | R2 | two tiers, below | error / warning | reliable / heuristic |
| Bare division | R8 | `find_all(exp.Div)`, exempting a non-zero literal divisor | error | **reliable** |
| Bad type literal | dialect | `exp.Cast(...).to` in `{FLOAT, INT, BOOLEAN}` | error | **reliable** |
| Non-additive SUM | R4/R5/R6 | two tiers, below | error / warning | reliable / heuristic |

**Unknown column, two tiers.** `geo-play-intel`'s `_find_invalid_columns`
(`bigquery_source.py:20-80`) is the right shape but collects every column name into one bag and
checks the *union*, so it structurally cannot catch "exists in A, used on B" — exactly what its own
strict-column rule is about. So:

- **Tier 1, error, reliable** — name appears in *no* shortlisted table, after skipping CTE aliases
  (`exp.CTE.alias`), column aliases (`exp.Alias.alias`), table/subquery aliases, and struct field
  access. What remains unmatched is a genuine hallucination.
- **Tier 2, warning, heuristic** — resolve `alias.col` back to a concrete table via
  `exp.Table`/`exp.TableAlias` and flag a mismatch. Warning only: alias resolution through CTEs with
  derived projections yields false positives, and a false error would burn a repair round on correct
  SQL.

**Non-additive SUM, two tiers** — the highest-value check:

- **Tier 1, error, reliable in practice** — for each `exp.Sum`/`exp.Avg`, look for an `exp.EQ` in the
  same scope whose left side is a `metric_id` column and right side a string literal. Look that id up
  in the catalogue; if its `aggregation_type != "sum"` and the aggregate is
  `SUM(value)`/`SUM(observed_value)`/`SUM(numerator)`-without-denominator, that is definite. Both
  facts come straight off the AST, and it catches the likeliest failure against the long/narrow
  tables.
- **Tier 2, warning, heuristic** — identifier patterns inside `exp.Sum` against
  `{*_rate, *_pct, *_ratio, dau, wau, mau, arpu, arppu, arpdau, avg_*}`. Warning, because
  `SUM(retained_users)` is legitimate and name-based classification over-triggers.

**Cannot be checked without a warehouse** — state this in the README and surface it via the envelope:
whether the grain claim is true; whether a join key fans out; whether the chosen date column is the
right one; whether rows for `metric_id = 'dau'` exist in the window; whether the **numbers** are
right. `GeneratedSql.grain` and `.assumptions` exist to make those explicit for a human spot-check
rather than hiding them.

**`sqlglot` degradation.** Load-bearing for the read-only check, single-statement, `exp.Div`,
`SUM(...)` argument extraction, and `metric_id = 'x'` literal extraction. Guard the import; when
absent, `validate()` sets `parser="regex-fallback"`, `parsed_ok=False`, marks **every** issue
`reliable=False`, and drops confidence to `low`. Fallback: comment-stripped leading-keyword
allowlist, naive semicolon count (breaks inside string literals — acknowledged), and keyword scans.

**Repair loop** — `max_repairs = 2`, so ≤3 generation calls + 1 router call:

```
shortlist = shortlister.shortlist(question)
for attempt in 1 .. max_repairs + 1:
    payload = call_model(build_messages(question, shortlist, prev_sql, prev_report))
    if payload["unsupported_reason"]: return unsupported envelope, sql = ""
    sql = extract_sql_from_payload(payload)
    report = validator.validate(sql)
    if report.ok: break
    if "R1_READ_ONLY" in report.signature: return refused, sql = ""   # never hand back DML
    if report.signature == prev_report.signature: break               # model repeating itself
    prev_sql, prev_report = sql, report
return GeneratedSql(..., attempts=attempt, validation=report)
```

Only `severity == "error"` triggers a repair; warnings ride along and affect confidence only. On
exhaustion **return** the last attempt with `validation.ok == False` — do not raise; the caller and
the exit code decide. Sole exception: a read-only violation never comes back as a SQL string.

---

## 6. Output envelope

```python
@dataclass(frozen=True)
class GeneratedSql:
    question: str
    sql: str                       # "" when unsupported or refused
    dialect: str                   # "bigquery"
    metrics_used: tuple[str, ...]  # model's claim, cross-checked against metric_id literals
    tables_used: tuple[str, ...]   # from the AST, NOT the model's claim
    assumptions: tuple[str, ...]
    grain: str
    explanation: str
    validation: ValidationReport
    confidence: str                # high|medium|low — COMPUTED, never asked of the model
    confidence_reasons: tuple[str, ...]
    attempts: int
    unsupported_reason: str | None  # non-None => sql == ""
    model: str
    shortlisted_tables: tuple[str, ...]
    shortlisted_metrics: tuple[str, ...]
    def to_dict(self) -> dict[str, object]
```

Two deliberate choices:

- **`tables_used` comes from the AST.** The model's self-report of what it used is precisely the
  thing you cannot trust; `exp.Table` is ground truth. `metrics_used` has no AST equivalent so it
  stays a claim — the validator cross-checks it against `metric_id = '…'` literals and disagreement
  is a warning.
- **`confidence` is computed.** LLMs judge their own SQL poorly. Start `high`; drop to `medium` on
  any warning, any shortlisted metric with `inferred`/`unknown` provenance, any referenced column
  whose dictionary `confidence` is `medium`/`low` (this is what finally makes that field earn its
  keep — 98 medium + 2 low rows exist), or `attempts > 1`. Drop to `low` on `parsed_ok is False`, the
  regex fallback, a surviving error, or a selected metric whose `observability_status != "live"`.
  `confidence_reasons` records which clause fired, so it is auditable rather than magic.

---

## 7. CLI

```
python sql_generation.py "how many DAU last 7 days"
```

`--json` full envelope · `--sql-only` pipe-friendly · `--no-router` keyword-only, saves a call ·
`--show-prompt` print assembled messages and exit, **no API call** · `--max-repairs` ·
`--model` (default `$OPENROUTER_MODEL`) · `--schema` / `--dictionary` / `--catalogue`.

Exit codes: `0` valid SQL · `1` SQL produced but errors remain · `2` unsupported/refused, no SQL ·
`3` config or API error. A missing `OPENROUTER_API_KEY` or missing catalogue exits `3` with a
one-line message naming the fix.

**Build `--show-prompt` first.** It needs no API key and makes the whole assembly path inspectable —
it is how retrieval and rule wording actually get debugged.

---

## 8. Evaluation

`eval/golden_questions.json` — ~20 cases, each pinning one rule:

| id | question | pins |
|---|---|---|
| `dau_7d` | how many DAU last 7 days | R5 — `COUNT(DISTINCT)`, forbid `SUM(value)` |
| `mau_from_dau_trap` | estimate MAU from our DAU numbers | R7 |
| `arpu_month` | what was ARPU in January | R6 — parts, not `AVG` |
| `retention_d7` | D7 retention for last month's cohorts | R3 + right-censoring caveat |
| `revenue_total` | total IAP revenue last 30 days | R4 — the case that *may* be summed |
| `whales` / `stickiness` / `churn` | — | **retrieval only**, zero lexical anchor |
| `bare_div` | revenue per active user last week | R8 |
| `float_cast` | cast ARPU to a float | dialect — `FLOAT64` |
| `hallucination_bait` | what's the average player IQ | R12 — expect unsupported |
| `readonly_bait` | delete all test users | R1 — expect refusal, `sql == ""` |
| `no_date_unless_asked` | total sessions last week | R10 |
| `unobservable` | tournament completion rate | `observability_status` → confidence `low` |

`eval_sql_generation.py` asserts, without executing SQL: `validation.ok`; every `require_regex`
matches and no `forbid_regex` does; `expect_metrics ⊆ metrics_used`; `tables_used ∩
expect_tables_any_of` non-empty; every referenced column exists in the dictionary;
`bool(unsupported_reason) == expect_unsupported`; `expect_confidence_at_most` where given.

`--retrieval-only` runs **just** the shortlister and asserts only the metric/table expectations — one
cheap call per case. Retrieval is the component most likely to regress silently (add a synonym,
reword the router prompt) and the cheapest to test, so it gets its own fast loop.

---

## 9. What survives from the current file

**Verbatim: nothing.** All three imports are unresolvable here and the class is `async` against a
sync requirement. Calling this a refactor would be misleading — it is ~95% new code with one
salvaged function.

**Kept with edits — one thing.** `_extract_sql`'s fallback ladder (JSON `{"query": …}` → ```` ```sql ````
fence → any fence) is a good idea; promote it to a module-level `extract_sql(raw: str) -> str` with
three changes: (1) **delete the final fall-through** — return `""` so prose is reported as "no SQL in
response" instead of becoming a bogus parse error; (2) **drop the unconditional `+ ";"`** — it fights
the single-statement check for no benefit since nothing executes; (3) treat it as a ~8-line safety
net only, since `json_object` mode makes the JSON branch hit essentially always.

The class docstring — *"Converts natural-language analytics asks into executable SQL"* — carries over
to `SqlGenerator`. It is the one sentence still true.

**Deleted:** all three imports; `_normalize_content` (~17 lines) and `_extract_response_text`
(~22 lines), whose entire job is unwrapping langchain's polymorphic `content` — with the raw `openai`
client, `response.choices[0].message.content` is a plain `str`; `_build_system_prompt` (~9 lines);
the `async`/`ainvoke` path; the whole tool-calling agent construction (there is no tool to call —
nothing is executed, so one chat completion is the right shape); the `Optional[Any]` model param.
**~55 of 118 lines are pure langchain-envelope plumbing.**

---

## 10. Order of work

Steps 1–4 need **no API key and no network** — deliberately front-loaded so most of the system is
verifiable offline before a token is spent.

| # | Step | Verify by |
|---|---|---|
| 1 | `validate_metric_catalogue.py`; run it on the user's `metric_catalog.json` | totals; zero duplicate ids; the `unknown` `aggregation_type` count; how many `source_tables` resolve |
| 2 | `sql_knowledge.py` — dataclasses, `KnowledgeBase.load`, index renderers | 50 tables / 948 columns; `columns_for(["fact_user_activity_daily"])` → 9 names; zero join warnings between `schema.json` and `data_dictionary.json` |
| 3 | `sql_prompts.py` — `SYSTEM_PROMPT` R1–R12 + renderers | `__main__` prints a rendered block for a hand-picked table list; token-count it |
| 4 | `sql_validation.py` **before** the generator, so the generator develops against a working oracle | ~15 hand-written good/bad SQL fixtures, one per rule, each producing the expected `rule` + `severity` |
| 5 | `sql_generation.py` — `extract_sql`, `GeneratedSql`, `SqlGenerator`, repair loop, CLI. `--show-prompt` first, then the live call. Keyword-only shortlisting at this stage | `--show-prompt` renders; then one real question end-to-end |
| 6 | `Shortlister._route` — the LLM router. Last, because keyword-only already unblocked step 5 | `--retrieval-only` passes `whales`, `stickiness`, `churn` |
| 7 | `eval/golden_questions.json` + `eval_sql_generation.py` | full run; triage failures into rule-wording vs retrieval vs catalogue-data bugs |
| 8 | `requirements.txt += sqlglot`; short README section | fresh install; then confirm the no-`sqlglot` fallback still runs |
| 9 | Install the html-doc skill to `.claude/skills/html-doc/` from the `.skill` zip | `SKILL.md` frontmatter parses; `python .claude/skills/html-doc/scripts/verify_html.py --help` runs |
| 10 | Produce `nl_to_sql_architecture.html` via the skill, with the step-by-step enhancement ledger | run `verify_html.py` on it; report SVG well-formedness, tag balance, both themes, page-count estimate |

### Riskiest part: `aggregation_type` coverage in the user's catalogue

Everything downstream keys off that one field — R4/R5/R6 in the prompt, the Tier-1 additivity
validator, and the confidence score. If it is wrong, the system enforces the **wrong** aggregation
with full confidence, which is worse than having no rule. In the upstream seed only 47 of 190 rows
declare it. Mitigations, in order of how much they help: `unknown` is never guessed past and is
treated as non-additive; provenance is rendered into the prompt as `(inferred)` and R3 tells the
model to prefer the conservative aggregation when it sees that; provenance caps reported confidence
at `medium`; and `validate_metric_catalogue.py` puts the coverage number in front of the user before
the first run.

**Second-riskiest: table shortlisting**, because the metric→table bridge is broken (§2). Build and
test it as "router selects tables from the data dictionary; metrics only *add*" from the start.

---

## 11. Task 4 — the HTML document

1. Install the skill from `C:\Users\KireetiChennuru\Downloads\html-doc.skill` (a zip containing
   `html-doc/SKILL.md` and `html-doc/scripts/verify_html.py`) to
   `c:\Repository\geo-play-ai-intel\.claude\skills\html-doc\`.
2. **Caveat:** a project skill created mid-session may not register until Claude Code restarts. If
   `/html-doc` is not invocable, follow `SKILL.md` directly — identical output, and I will say which
   path was taken.
3. Write `nl_to_sql_architecture.html` at the repo root (beside `concepts.html`): a **local file**,
   so the Google Fonts `@import` is used, per the skill's render-target rule.
4. Sections per the skill: `00` problem/shape · `01` fit + the hand-authored inline-SVG diagram
   (horizontal bands per stage, **grey = pre-existing, colour = added by this work**) · `02` what was
   implemented in order · `03` files and what each owns, with the authored-vs-generated boundary
   unmissable · `04` concepts (additivity, long/narrow metric tables, provenance) · `05` how it runs,
   **including what does NOT happen** — no SQL execution, no BigQuery credential, no dry-run ·
   `06` validation gates in order and what each can and cannot catch · `07` versions and
   dependencies (`+ sqlglot`, and what deliberately did not change) · `08` verified results and open
   items.
5. The **step-by-step enhancement ledger** is the spine of `02`: one numbered entry per enhancement,
   each recording what changed, why, and how it was verified.
6. Corrections callouts are mandatory and get the beliefs that turned out false — including the two
   found while planning: that the metric seed was one uniform table (it is two disjoint vintages),
   and that `source_tables` could ground table selection (it cannot; 126 of 190 rows say
   `"Aggregated marts"`).
7. Hard rules from the skill: **no code, commands, or config blocks anywhere** — prose only, with
   identifiers named inline. Every factual claim traces to something verified this session; anything
   unverified says so in words. Target ~6–7 printed pages; do not force a page break per section.
8. Run `scripts/verify_html.py` on the finished file and fold its output into the report: SVG
   well-formedness, tag balance, text inside the `viewBox`, grid child counts, page-count estimate.
   Then state the page count, and confirm both themes define their variables and that the toggle
   swaps them.

---

## 12. Verification, end to end

```
python validate_metric_catalogue.py                       # contract audit, offline
python sql_knowledge.py                                   # 50 tables / 948 cols / N metrics
python sql_prompts.py                                     # rendered blocks + token count
python sql_validation.py                                  # fixture table, all rules fire
python sql_generation.py --show-prompt "how many DAU last 7 days"    # no API call
python sql_generation.py "how many DAU last 7 days"       # live; expect COUNT(DISTINCT)
python sql_generation.py --json "what was ARPU in January"            # expect SAFE_DIVIDE of parts
python sql_generation.py "delete all test users"          # expect exit 2, sql == ""
python eval_sql_generation.py --retrieval-only            # cheap retrieval pass
python eval_sql_generation.py                             # full golden run
python .claude/skills/html-doc/scripts/verify_html.py nl_to_sql_architecture.html
```

Success: `dau_7d` emits `COUNT(DISTINCT user_id)` and never `SUM(value)`; `arpu_month` emits
`SAFE_DIVIDE(SUM(numerator), SUM(denominator))`; `readonly_bait` returns no SQL at exit 2;
`whales` shortlists a segment table with no lexical anchor in the question; `verify_html.py` reports
zero hard problems.

**Nothing in this plan executes SQL or holds a BigQuery credential.** The only network egress is
OpenRouter.
