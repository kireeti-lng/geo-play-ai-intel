# OpenRouter connection script for `geo-play-ai-intel`

## Context

`c:\Repository\geo-play-ai-intel` is an empty greenfield directory — a single 0-byte `main.py`, no dependency file, no config, no README, no LLM client of any kind. The goal is a working, verifiable entry point that authenticates against OpenRouter and completes one chat call, so the directory goes from "empty placeholder" to "proven connection you can build an intel pipeline on top of."

OpenRouter is an OpenAI-compatible gateway (`https://openrouter.ai/api/v1`), so this is a provider-neutral implementation using the `openai` SDK with an overridden `base_url` — not Anthropic SDK code. Model IDs are `vendor/model` slugs (e.g. `anthropic/...`, `openai/...`), which is why the script includes slug discovery rather than relying on a hardcoded default alone.

Two environment facts that shape the plan:

- **There is no git repo here.** `C:\.git` has `worktree = C:/` and remote `kireeti-lng/project_files`, so this directory is inside a repo spanning the whole C: drive. A `.gitignore` placed in this directory *does* apply to this subtree, so it is the correct place to protect `.env`. No `git init` and no commits are part of this plan.
- **No conventions exist locally.** Config naming follows the sibling project `c:\Repository\geo-play-data-connector` (`src\core\settings.py`): unprefixed `SCREAMING_SNAKE_CASE` env vars, `.env` gitignored.

## Decisions (confirmed with the user)

| Choice | Decision |
|---|---|
| Scope | Connection test + one chat call; print reply, model, token usage |
| HTTP layer | `openai` SDK with `base_url` pointed at OpenRouter |
| Config | `OPENROUTER_API_KEY` from `os.environ`, `.env` fallback via `python-dotenv` |

## Files

### `main.py` — the script

Keeping the existing (misspelled) filename since it's the path given. Renaming to `main.py` is a one-line follow-up if wanted; not doing it unprompted.

Structure, top to bottom:

1. **Constants** — `BASE_URL = "https://openrouter.ai/api/v1"`, `DEFAULT_MODEL`, `APP_TITLE`, `SITE_URL`.
2. **`load_config()`** — `load_dotenv()` (no-op when `.env` is absent), then read `OPENROUTER_API_KEY` (required) and `OPENROUTER_MODEL` (optional, falls back to `DEFAULT_MODEL`). Missing key exits with a one-line actionable message naming the env var and `.env.example`, not a traceback.
3. **`build_client(api_key)`** — returns `OpenAI(base_url=BASE_URL, api_key=api_key, default_headers={"HTTP-Referer": SITE_URL, "X-Title": APP_TITLE})`. Those two headers are OpenRouter's optional app-attribution headers; harmless and conventional to send.
4. **`list_models(client)`** — `client.models.list()` against OpenRouter's `/models`, printing slugs. Reached via `--list-models`.
5. **`chat_once(client, model, prompt)`** — one `client.chat.completions.create(...)` call, non-streaming. Returns the message text plus `response.model` and `response.usage`.
6. **`main()`** — `argparse` with a positional `prompt` (default: a short fixed self-test prompt) and a `--list-models` flag. Prints resolved model, reply, and `prompt_tokens`/`completion_tokens`.
7. **Error handling** — catch `openai.AuthenticationError` (bad/expired key → say so plainly), `openai.NotFoundError` / `openai.BadRequestError` (likely a stale or wrong model slug → print the failing slug and suggest `--list-models`), `openai.RateLimitError`, and `openai.APIConnectionError`. Catch the specific classes in a most-specific-first chain, not one broad `except`.

**On `DEFAULT_MODEL`:** I will not assert a slug from memory. I'll set a default constant, then verify it against the live `GET /models` response on the first real run and correct the constant if it isn't currently served. The `--list-models` flag and the not-found handler exist precisely so a stale default is self-diagnosing rather than a confusing 400.

### `requirements.txt`

```
openai>=1.0
python-dotenv>=1.0
```

Plain `requirements.txt` rather than `pyproject.toml` — this is one script, not a packaged project. If it grows, the sibling project's `pyproject.toml` + `uv.lock` layout is the pattern to copy.

### `.env.example`

Committed template with empty values — `OPENROUTER_API_KEY=`, `OPENROUTER_MODEL=`, plus a comment pointing at `--list-models` for valid slugs. No real key ever goes in this file.

### `.gitignore`

```
.env
__pycache__/
*.pyc
```

`.env` first — the load-bearing line, given this directory sits inside the C:-drive-wide repo.

## Verification

Run in order from `c:\Repository\geo-play-ai-intel`:

1. **Install** — `pip install -r requirements.txt` (or into whatever venv you prefer; I'll ask before creating one).
2. **Missing-key path** — run with `OPENROUTER_API_KEY` unset and no `.env`. Expect the one-line "set OPENROUTER_API_KEY" message and a non-zero exit, no traceback.
3. **Auth + discovery** — set a real key, then `python main.py --list-models`. A populated slug list proves the key, base URL, and headers are all correct. Confirm `DEFAULT_MODEL` appears in that list; if not, correct the constant and note the change.
4. **The actual chat call** — `python main.py "Reply with exactly: connection ok"`. Expect the reply text, the resolved model slug, and non-zero token counts.
5. **Bad-model path** — `OPENROUTER_MODEL=vendor/does-not-exist python main.py "hi"`. Expect the friendly not-found message suggesting `--list-models`, not a raw API error dump.
6. **`.env` fallback** — unset the shell env var, put the key in `.env`, re-run step 4. Confirm it still works, and that `git status` does not list `.env`.

Steps 3–5 need a real OpenRouter API key. I'll write all the files and run steps 1, 2, and 5 (which need no key); tell me when the key is in place and I'll finish steps 3, 4, and 6 and report the actual output.
