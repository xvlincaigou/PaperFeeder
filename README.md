# PaperFeeder

PaperFeeder is a daily paper-and-blog digest pipeline with Semantic Scholar based personalization and a feedback loop.

**中文说明：** [README.zh-CN.md](README.zh-CN.md)

## Final Layout

```text
PaperFeeder/
├── paperfeeder/          # Main Python package
├── scripts/              # Bootstrap and feedback helper scripts
├── cloudflare/           # Feedback worker and D1 schema
├── state/semantic/       # Persistent personalization state
├── artifacts/            # Per-run generated manifests/templates
├── user/                 # User-editable settings and prompts
├── tests/                # Test suite
├── config.yaml           # Project defaults
└── main.py               # Main digest entrypoint
```

## What Each Directory Means

`paperfeeder/`

- All real application code lives here now.
- Flat, obvious modules at the top: `models.py` (papers/authors), `email.py` (senders), `chat.py` (OpenAI-style chat client).
- The main pipeline is under `paperfeeder/pipeline/runner.py`.
- Feedback apply CLI lives in `paperfeeder/cli/apply_feedback.py`.

`state/semantic/`

- `state/semantic/seeds.json` stores long-lived positive and negative Semantic Scholar seed IDs.
- `state/semantic/memory.json` stores recently seen paper keys so repeated papers can be suppressed.
- This is runtime state, not source code.

`artifacts/`

- This contains generated run outputs such as `run_feedback_manifest_*.json` and `semantic_feedback_template_*.json`.
- It is disposable runtime output and is ignored by git.

`cloudflare/`

- `cloudflare/feedback_worker.js` is the only feedback worker source.
- `cloudflare/d1_feedback_events.sql` is the D1 schema.

## Setup

```bash
bash scripts/bootstrap.sh
source .venv/bin/activate
```

Then fill in `.env`, and optionally adjust `user/settings.yaml`, `user/research_interests.txt`, and `user/prompt_addon.txt`.

## How To Run

Main digest:

```bash
python main.py --dry-run
python main.py --days 3
```

`--dry-run` writes `report_preview.html` locally and may generate feedback files under `artifacts/`.

**Lightweight debug (one paper, no crawl):** use a JSON fixture instead of fetching arXiv/HF/S2. Skips keyword+LLM filters and Tavily enrichment. **By default, `--debug-sample` does not call the main digest LLM** — it sends a small fixed HTML body (good for testing email, feedback, D1). Copy `user/debug_sample.example.json` to `user/debug_sample.json` and edit.

```bash
# Stub HTML only, no main digest LLM; local preview (omit --dry-run to send email)
python main.py --debug-sample --dry-run

# Same stub, real email via Resend
python main.py --debug-sample

# Debug sample but use the real summarizer LLM for the report body
python main.py --debug-sample --debug-llm-report --dry-run

# Full fetch, but stub report body (no main digest LLM)
python main.py --debug-minimal-report --dry-run

# Custom fixture path
python main.py --debug-sample --debug-sample-path path/to/papers.json --dry-run
```

Optional: `--debug-write-memory` updates `state/semantic/memory.json` (default in debug sample mode is to skip it).

Apply reviewed feedback from a manifest:

```bash
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
python -m paperfeeder.cli.apply_feedback --manifest-file artifacts/run_feedback_manifest_<run_id>.json
```

Apply pending feedback from Cloudflare D1:

```bash
python -m paperfeeder.cli.apply_feedback --from-d1 --manifest-file artifacts/run_feedback_manifest_<run_id>.json --manifests-dir artifacts --dry-run
```

There is also a wrapper if you prefer scripts:

```bash
python scripts/semantic_feedback_apply.py --manifest-file artifacts/run_feedback_manifest_<run_id>.json --dry-run
```

## Configuration

Defaults live in `config.yaml`. The semantic state paths are:

```yaml
semantic_scholar_seeds_path: "state/semantic/seeds.json"
semantic_memory_path: "state/semantic/memory.json"
```

Config precedence is:

1. `config.yaml`
2. `user/settings.yaml`
3. environment variables
4. `user/research_interests.txt` and `user/prompt_addon.txt`

## Feedback Flow

1. `python main.py` generates a digest.
2. The run may export manifest/template files into `artifacts/`.
3. Feedback links point to the worker in `cloudflare/`.
4. Reviewed feedback is applied back into `state/semantic/seeds.json`.

**One-click in email (👍 / 👎):** set `FEEDBACK_ENDPOINT_BASE_URL` to your deployed worker base URL and `FEEDBACK_LINK_SIGNING_SECRET` to the same secret configured on the worker. Without both, the manifest has no signed URLs and the HTML will not show working feedback links. The outgoing email uses the same per-paper links as the web/D1 viewer (plain `GET` to `/feedback?t=...`; most mail clients ignore the optional in-email JavaScript).

The **“Open Feedback Web Viewer”** banner is optional: it only adds a link to the browser copy at `/run?run_id=...` (useful if email layout breaks or you want to share the digest). Per-paper 👍/👎 do **not** depend on it. To hide the banner, set `FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL=false` or `feedback_web_viewer_link_in_email: false` in `user/settings.yaml`. D1 upload and `/run` URLs still work if you open them manually.

### Configure feedback (checklist)

Copy `.env.example` → `.env` and fill the variables below. Env vars override `config.yaml` / `user/settings.yaml` (see `paperfeeder/config/schema.py`).

| What | Where to set | Notes |
|------|----------------|------|
| **Worker URL** | `.env` → `FEEDBACK_ENDPOINT_BASE_URL` | Example: `https://paperfeeder-feedback.your-subdomain.workers.dev` — **no trailing slash**. This is where signed links in the email point. |
| **Signing secret** | `.env` → `FEEDBACK_LINK_SIGNING_SECRET` **and** Worker | Must be **identical**. On Worker: `cd cloudflare && cp wrangler.toml.example wrangler.toml` (edit `database_id`), then `npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET` and paste the same string. Used to mint and verify `t=` tokens. |
| **D1 + Worker** | Cloudflare Dashboard or Wrangler | Worker code expects binding name **`DB`** (see `cloudflare/wrangler.toml.example`). Apply schema once: `npx wrangler d1 execute <DB_NAME> --remote --file=cloudflare/d1_feedback_events.sql`. |
| **Python → D1** | `.env` → `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `D1_DATABASE_ID` | Lets the digest run **upload** HTML to `feedback_runs` (web viewer at `/run?run_id=...`). **Apply feedback from D1** uses the same three. `D1_DATABASE_ID` must be the **same** database the Worker uses. |
| **Semantic Scholar id** | `.env` → `SEMANTIC_SCHOLAR_API_KEY` (recommended) | Manifest only adds `action_links` when `semantic_paper_id` is known. Resolver uses the API for arXiv/HF-style papers; a key reduces empty buttons. |
| **Web viewer banner in email** | `.env` → `FEEDBACK_WEB_VIEWER_LINK_IN_EMAIL` (default `true`) | Set `false` to omit the “Open Feedback Web Viewer” block; 👍/👎 stay as-is. Use a real YAML boolean in `user/settings.yaml` (`false`), not a quoted string (`"false"` is treated as enabled unless you use the env var). |
| **Feedback JSON attachments** | `.env` → `FEEDBACK_EMAIL_ATTACHMENTS` (default `all`) | `all` = manifest + questionnaire template (two files). `manifest` = only `run_feedback_manifest_*.json`. `none` = no attachments. Files are still written under `artifacts/`. |

**Deploy Worker (minimal flow)**

```bash
cd cloudflare
cp wrangler.toml.example wrangler.toml
# Edit wrangler.toml: set database_id from `wrangler d1 create paperfeeder-feedback`
npx wrangler d1 execute paperfeeder-feedback --remote --file=d1_feedback_events.sql
npx wrangler secret put FEEDBACK_LINK_SIGNING_SECRET
npx wrangler deploy
```

Then set `FEEDBACK_ENDPOINT_BASE_URL` in `.env` to the deployed URL (Wrangler prints it).

## GitHub Actions, `seeds.json`, and what “memory” does

If you use the workflows under `.github/workflows/`:

| Workflow | What it does with state |
|----------|-------------------------|
| **Daily digest** (`daily-digest.yml`) | Checks out `main`, **loads** `state/semantic/seeds.json` and `memory.json` from the **state branch** (default `memory-state`, overridable with repo variable `SEED_STATE_BRANCH`), runs `main.py`, then **pushes** updated **`memory.json`** back to that branch. |
| **Apply feedback** (`apply-feedback-queue.yml`) | **Loads** `seeds.json` from the state branch, runs `python -m paperfeeder.cli.apply_feedback --from-d1` to merge **pending** rows in D1 into seeds, then **pushes** updated **`seeds.json`** back. Also runs on a **schedule** (default: every 6 hours at :30 UTC — edit the `cron` in the workflow file to change). Manual runs still default to **dry run** unless you uncheck it. |

### How `seeds.json` affects the digest (not a separate “AI agent”)

There is no extra agent process: the **same** `main.py` pipeline reads the file.

- When **`semantic_scholar_enabled`** is on, `SemanticScholarSource` (`paperfeeder/sources/paper_sources.py`) reads `semantic_scholar_seeds_path` (default `state/semantic/seeds.json`).
- It sends those IDs to Semantic Scholar’s **recommendations** API as `positivePaperIds` / `negativePaperIds`, so 👍/👎 (after apply) **steer which S2 recommendations** get merged into the candidate paper list.
- **`memory.json`** is separate: it tracks recently **seen** items so they can be suppressed from recommendations (TTL / caps in config).

So: updated seeds **do not** fine-tune an LLM; they change the **S2 recommendation request**. arXiv / blogs / manual sources are unaffected by seeds, except where shared **memory** dedupes “already seen” papers.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Notes

- `artifacts/` and `llm_filter_debug/` are ignored runtime output directories.
- GitHub Actions also read and persist `state/semantic/seeds.json` and `state/semantic/memory.json` on the state branch; see **GitHub Actions, `seeds.json`, and what “memory” does** above.
