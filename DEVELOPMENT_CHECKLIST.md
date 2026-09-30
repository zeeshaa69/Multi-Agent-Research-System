# Development checklist

Results below come from an actual run of `./scripts/verify.sh` (Python 3.11.15, Node 22.22.2, npm 10.9.7, ruff 0.16.9, mypy 2.3.1, pytest 9.1.1) on Linux. Re-run it to reproduce.

## Automated gates

| Check | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check src tests` | passed, no findings |
| Formatting | `ruff format --check src tests` | passed (43 files formatted) |
| Type checking (backend, strict) | `mypy` | passed, 34 source files, no issues |
| Backend tests | `pytest -q` | 61 passed, 0 failed (one third-party deprecation warning from the test client) |
| Offline end-to-end (CLI) | `researcher run "<question>" --offline` | completed; report contains all four statement labels (source-supported, uncertain, conflicting, generated synthesis) |
| Frontend lint | `npm run lint` (oxlint) | passed |
| Frontend type check | `npm run typecheck` (tsc) | passed |
| Frontend build | `npm run build` | passed (24 modules; JS 238.6 kB, CSS 9.5 kB) |

## Manual end-to-end check of the dashboard

The API was started with `researcher serve --offline` and the built dashboard was driven with headless Chromium (Playwright):

- Submitted a question through the form; the pipeline view showed stages progressing while the job ran.
- On completion the report showed all four statement kinds; clicking a conflicting statement opened the provenance inspector with claims, supporting and conflicting quotes, and sources.
- Claims, Sources and Agent log tabs rendered.
- No browser console errors or page errors were recorded.

Screenshots from this check were reviewed but deliberately not committed.

## Behaviour verified by tests

- Planner: topic extraction, aspect selection, limits, determinism, valid and invalid model plans.
- Agent routing: one agent per task kind, unknown kind raises, dependency ordering, bounded parallelism, skipped dependents, fan-out graph.
- Retries: backoff schedule, success after transient failures, no retry of permanent errors, exhaustion degrades to an honest empty report, model client error mapping.
- Source extraction: verbatim quotes, required source fields and hash, quote grounding levels, rejection of model claims whose quotes are not in the source, HTML text extraction, fetcher safety (private addresses, schemes, robots.txt, size cap).
- Citation mapping: dropped citations for missing source, altered source text, missing quote; report-level validation; every sourced statement in a real offline run resolves to a stored source and quote.
- Conflicting evidence: numeric and negation conflicts recorded on both sides, unit-aware number comparison, corroboration and confidence, hedged claims, unsupported and drifted claims.
- Report generation: all statement kinds, determinism across runs, out-of-corpus question gives "no usable evidence", Markdown labels, statistics, guarded model overview.
- API: full job lifecycle, validation errors, 404s, history persistence, interrupted jobs marked failed.

## Known gaps

- Ollama and llama.cpp clients were exercised only through mocked HTTP and a scripted stand-in model. No real local model was available in this environment, so live-model quality is unmeasured.
- The Wikipedia/HTTP live retrieval path was tested only with mocked transports, not against the real network.
- No benchmarks were run; none are claimed.
- The frontend has no automated component tests (type check, lint, build and the manual browser check only).
