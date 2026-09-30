# Local Multi-Agent Research System

A research workflow in which seven specialised agents collaborate to answer a question, running entirely on your machine. It uses a real task queue with dependencies, parallel workers, retries with backoff, and structured logs. Every statement in the final report is labelled as **source-supported**, **uncertain**, **conflicting** or **generated synthesis**, and the dashboard lets you trace each one back to the exact quote and source.

- No paid or cloud AI APIs. Language-model support is optional and limited to local servers (Ollama, llama.cpp).
- A deterministic **offline mode** (fixture corpus, no network, no model) runs the complete workflow and powers the test suite.
- Sources and findings are never invented: a claim is only reported if its verbatim quote is found in a stored source text.

> The bundled fixture corpus is **synthetic test data** (a fictional "Harborview Tidal Pilot"). Reports produced in offline mode demonstrate the workflow; they are not research findings. See [`fixtures/README.md`](fixtures/README.md).

## Architecture

```
User question
   │
   ▼
Planner ──► sub-questions
   │
   ▼  (task queue, dependency graph, N workers)
┌──────────────── per sub-question, in parallel ────────────────┐
│ Research task ──► sources ──► Extraction task ──► claims      │
└────────────────────────────────────────────────────────────────┘
   │  (aggregate step tolerates failed branches)
   ▼
Fact checker ──► Citation validator ──► Synthesis ──► Report writer
```

| Piece | Location |
| --- | --- |
| Task queue (deps, workers, timeouts, retries) | `src/researcher/orchestration/queue.py` |
| Agent routing (task kind → agent) | `src/researcher/orchestration/router.py` |
| Task graph + job runner | `src/researcher/orchestration/pipeline.py` |
| Job manager (background jobs, history) | `src/researcher/orchestration/manager.py` |
| Agents | `src/researcher/agents/` |
| Retrieval adapters | `src/researcher/retrieval/` |
| Local model clients | `src/researcher/llm/` |
| SQLite history | `src/researcher/storage.py` |
| HTTP API | `src/researcher/api.py` |
| Dashboard | `frontend/` (React + TypeScript + Vite) |

If a research or extraction task fails after its retries, the job continues: the affected sub-question is reported as having no usable evidence and a warning is attached to the job. If planning, fact checking, citation validation, synthesis or report writing fails, the job is marked failed.

## Agent responsibilities

| Agent | Responsibility | Uses a model? |
| --- | --- | --- |
| Planner | Breaks the question into sub-questions with relevance keywords. | Optional; falls back to rules if output is invalid |
| Research | Searches and fetches documents per sub-question; stores sources with hash and timestamp; de-duplicates by content hash. | No |
| Extraction | Extracts claims, each with a verbatim evidence quote. Model output is dropped if the quote is not in the source. | Optional; falls back to rules |
| Fact checker | Re-verifies every quote against the stored text, checks the claim still matches its quote, groups agreeing claims across sources, detects conflicts, assigns status and confidence. | No (deliberately deterministic) |
| Citation validator | Checks each citation resolves: source exists, content hash matches, quote is present. Drops or demotes claims with broken citations. | No |
| Synthesis | Builds report sections from verified claims, reusing claim text and quotes verbatim. Only the overview is free text, always labelled generated synthesis. | Optional overview, guarded (see below) |
| Report writer | Assembles statistics and limitations, validates the whole report against the citation rules, renders Markdown. Refuses to emit an invalid report. | No |

## Data model

Defined in `src/researcher/models.py`.

**Source**: `url`, `title`, `retrieved_at`, `text`, `source_type`, `content_hash` (SHA-256 of `text`), `claims` (extracted claims, each with `quote`, `relevance`, `hedged`, `grounding`), `subquestion_ids`.

**Claim**: `claim`, `supporting_sources` (source id + quote), `confidence`, `verification_status` (`supported` | `uncertain` | `conflicting` | `unsupported`), `conflicting_evidence` (source, quote, reason), `notes`.

**Report statement**: `kind` (`source_supported` | `uncertain` | `conflicting` | `generated_synthesis`), `claim_ids`, `source_ids`, `confidence`. Only `generated_synthesis` statements may lack citations.

Also: `Job`, `SubQuestion`, `TaskRecord` (status, attempts, error), `AgentLogEntry`, `Report`.

### Verification rules

- **unsupported**: the quote is not found in the source, or the claim wording drifted from its quote (for example a number not present in the quote). Excluded from the report.
- **conflicting**: two claims on the same topic give different figures for the same unit, or one negates the other. Both sides are recorded on both claims.
- **uncertain**: every supporting source uses hedged wording (`may`, `suggests`, ...) or the quote matched only after ignoring case and punctuation.
- **supported**: everything else.
- **confidence** is a heuristic, not a probability: 0.55 for one source, 0.8 for two, 0.9 for three or more; ×0.6 when uncertain; for conflicts, capped at 0.6 and scaled by the share of supporting versus conflicting sources.

## Installation

Requires Python 3.11+ and Node 20+ (for the dashboard).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
```

Run the dashboard and API (the built frontend is served by the API):

```bash
researcher serve --offline            # http://127.0.0.1:8000
```

For frontend development, run `researcher serve --offline` and `npm run dev` in `frontend/` (port 5173, proxies `/api`).

## Offline mode

```bash
researcher run "What are the costs, risks and environmental effects of the Harborview Tidal Pilot?" --offline
```

Offline mode uses the fixture corpus in `fixtures/corpus/` and rule-based agents, so it needs neither internet access nor a model, and output is deterministic (covered by a test). It is the default: with no environment variables set, the system is offline.

The corpus is built to trigger every verification outcome (corroboration, numeric conflict, negation conflict, hedged claim, irrelevant distractors). A question outside the corpus produces an honest report with "no usable evidence" rather than invented content. `RESEARCHER_SIMULATED_LATENCY=0.3` adds a delay to fixture retrieval so the pipeline view is visible while jobs run.

## Live mode and local model configuration

Configure with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `RESEARCHER_RETRIEVAL` | `fixtures` | `fixtures` or `live` (Wikipedia public API search, plus any `seed_urls` you supply) |
| `RESEARCHER_LLM` | `none` | `none`, `ollama` or `llamacpp` |
| `RESEARCHER_OLLAMA_HOST` / `RESEARCHER_OLLAMA_MODEL` | `http://127.0.0.1:11434` / `llama3.2` | Ollama endpoint and model |
| `RESEARCHER_LLAMACPP_HOST` | `http://127.0.0.1:8080` | `llama-server` endpoint |
| `RESEARCHER_DB` | `data/history.sqlite3` | research history database |
| `RESEARCHER_MAX_WORKERS` | `4` | parallel tasks per job |
| `RESEARCHER_ALLOW_PRIVATE_HOSTS` | `0` | allow fetching private/loopback addresses |
| `RESEARCHER_RESPECT_ROBOTS` | `1` | honour robots.txt for fetched URLs |

```bash
ollama pull llama3.2
RESEARCHER_RETRIEVAL=live RESEARCHER_LLM=ollama researcher serve
```

With a model configured, the planner, extraction agent and overview writer use it. Model output is validated and never trusted: invalid plans and extractions fall back to the rules (logged as warnings), extracted quotes must exist in the source, and an overview is rejected if it cites no known claim or contains a number absent from the cited claims. Fact checking and citation validation never use a model.

## Example research workflow

Question: *What are the costs, risks and environmental effects of the Harborview Tidal Pilot?* (offline fixtures)

1. The planner produces four sub-questions (what it is, cost, environmental effects, risks).
2. Four research tasks run in parallel, each retrieving fixture documents; four extraction tasks pull out claims with quotes.
3. The fact checker finds that two documents give different construction costs and that one says the pilot requires dredging while another says it does not. Those become `conflicting` statements showing both quotes. A claim worded "may reduce regional electricity prices" becomes `uncertain`.
4. The citation validator confirms each citation resolves to a stored source.
5. Synthesis and the report writer produce the sectioned report; the dashboard shows it, and clicking any statement opens its provenance.

Run it yourself to see the exact output; `researcher run ... --json` prints the complete job record including logs.

## API

| Method and path | Description |
| --- | --- |
| `POST /api/jobs` | Start a job: `{"question": "...", "options": {"max_subquestions": 5, "sources_per_subquestion": 5, "seed_urls": []}}`. Returns 202 with a summary. |
| `GET /api/jobs` | Job summaries, newest first (research history). |
| `GET /api/jobs/{id}` | Full job: tasks, sub-questions, sources, claims, logs, report. |
| `GET /api/jobs/{id}/sources` / `claims` | Sources / verified claims. |
| `GET /api/jobs/{id}/logs?after=N` | Agent log entries with `seq > N`. |
| `GET /api/jobs/{id}/report` / `report.md` | Structured report / Markdown report. |
| `DELETE /api/jobs/{id}` | Delete a finished job. |
| `GET /api/config`, `GET /api/health` | Mode and health. |

Interactive docs are at `/docs` when the server is running.

## Frontend

The dashboard shows active jobs and research history, the seven-stage agent pipeline (status, parallel progress, retries, errors), and tabs for the report, verified claims (filterable by status), sources (metadata, hash, highlighted evidence quotes) and the agent log. Each statement carries a badge that uses text and icon, not colour alone, and a distinct border style. Clicking a statement opens the provenance inspector: claims, evidence quotes (supporting and conflicting), sources, and related agent log entries. Generated synthesis is shown with a dashed outline and "not sourced".

## Testing and quality checks

```bash
./scripts/verify.sh          # lint, format check, types, tests, offline end-to-end, frontend lint/typecheck/build
pytest                       # backend tests only
```

Tests cover the planner, agent routing and queue scheduling, retries and backoff, source extraction and quote grounding, the HTTP fetcher's safety checks, citation validation and mapping, conflicting evidence, report generation, determinism, and the API. Language-model paths are tested with a scripted stand-in model, not a real one. [`DEVELOPMENT_CHECKLIST.md`](DEVELOPMENT_CHECKLIST.md) records the results of an actual run.

## Limitations

- Claim agreement and conflict detection is lexical: token overlap, numbers grouped by following unit word, and negation words. It misses contradictions phrased differently and can misjudge unusual phrasing. It is not natural-language inference.
- The rule-based extractor selects sentences by keyword overlap with the sub-question; it can miss relevant sentences and include marginal ones.
- Corroboration counts distinct retrieved documents, not proven independence; syndicated copies with different text count as separate sources.
- Confidence scores are heuristics and should not be read as probabilities.
- Live retrieval covers Wikipedia search and user-supplied URLs only; there is no general web search adapter. HTML extraction is basic (no JavaScript rendering, PDFs unsupported).
- Live model paths (Ollama, llama.cpp clients) are covered by mocked-transport tests; they have not been exercised against a running model in this repository's checks.
- Model-written overviews are labelled generated synthesis and are guarded but not semantically verified.
- Single-process server; job state lives in memory while running and is saved to SQLite. Jobs interrupted by a restart are marked failed.

## Security

- The server binds to `127.0.0.1` by default and has **no authentication**; do not expose it to untrusted networks. CORS allows only the local Vite dev origin.
- The URL fetcher accepts only `http(s)`, resolves hostnames and refuses non-public addresses (loopback, private, link-local) unless `RESEARCHER_ALLOW_PRIVATE_HOSTS=1`, re-checks every redirect hop, caps response size, accepts only text content types, and honours `robots.txt`.
- Fetched content is treated as data: it is never executed, and the UI renders it as text (React escaping; only `http(s)` links are made clickable).
- Prompts embed retrieved text, so a malicious page could try to steer a local model. Mitigations are structural: model output is schema-checked, quotes must exist in the source, and verification does not rely on a model.
- Questions are length-limited (8–1000 characters). Respect the terms of any site you fetch from; Wikipedia text is CC BY-SA and needs attribution if redistributed.

## Roadmap

- Additional retrieval adapters (for example arXiv, a self-hosted search instance).
- Entailment-based verification using a local NLI model as an optional second opinion.
- PDF extraction and better boilerplate removal.
- Live progress streaming instead of polling.
- Per-source reliability weighting and independence detection.
- Exporting a full provenance bundle alongside the report.

## License

MIT, see [`LICENSE`](LICENSE).
