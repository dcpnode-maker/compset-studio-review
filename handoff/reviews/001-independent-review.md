# Independent review: Orders 001 and 002

Reviewer: GPT-6 independent review lane (did not implement the code)
Date: 2026-09-28
Scope: `compset/pipeline.py`, `compset/server.py`, `compset/__main__.py`, with `compset/normalize.py` and the offline tests for context.

## Finding

- **Low — reject non-integer JSON numeric inputs instead of silently coercing them.** `compset/pipeline.py:35-36` calls `int()` directly. Through the dashboard API, JSON `true` becomes `1`, and `1.9` becomes `1`, so the collected date range or guest count can differ from what the caller supplied without an error. I reproduced this with `context_from({'days': True})`, `context_from({'adults': True})`, and `context_from({'days': 1.9})`; all were accepted. Validate an integer representation before conversion (and explicitly reject booleans/floats), or require JSON integer types for API calls.

## Review notes

- No blocking financial-semantics issue found in the reviewed path: prices remain decimal strings; currency mismatch and ambiguous qualifiers yield unknown values; nightly display values do not populate stay totals; availability false is not described as booked.
- SQLite connection lifetime and repeat ingestion are sound in the reviewed implementation: the connection context commits before `closing` closes it, and the repeat-ingestion test confirms one run and four observations after persisting the same run twice.
- The request path has no caller-supplied target URL. The collector validates exact HTTPS Airbnb origins and known GET operations, disables redirects for replay, and stops on access/rate-limit responses. The dashboard binds to `127.0.0.1`, checks Host and POST Origin/custom header, validates before starting a worker, and rejects a second job while one is running. No SSRF or concurrent-job bypass was found in this review.
- The CLI `reparse` intentionally accepts a local evidence file and calls the same pipeline; no shell execution or remote file path is introduced by the dashboard API.

## Proof executed by reviewer

Command: `.venv\Scripts\python.exe -m unittest discover -s tests -v`

Result: **31 tests passed, 0 failed** (`Ran 31 tests in 1.120s`, `OK`). This included collection allowlist/access-limit/redaction tests, normalization and price parsing tests, SQLite idempotence/unknown-date tests, and loopback server origin/host/single-job tests.

Additional validation probe: directly called `context_from` with boolean and fractional JSON values; each was accepted and truncated/coerced as described above.
