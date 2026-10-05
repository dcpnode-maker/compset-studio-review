# Order 005 integration and live proof

28 September 2026. Parent Codex reviewed the separately authored `adaptive.py` and `nightly_rows.py`, integrated the workflow and CLI, and personally executed the proof below. The parent did not implement those two pure modules. Independent review of parent-owned orchestration is in review 007; independent review of the route implementation is in review 008. No changes were made to Yellow or its harness.

## Independent review of delegated modules

Reviewed the bounded adaptive plan, transition gate, hard bedroom/room-type/guest-floor rules, unknown-subject guard, callback coverage stops, duplicate retention, complete candidate audit and changed-radius reporting. Personally ran the 13 adaptive tests and the 11 nightly-row tests as part of a 51-test integration pass, then the final full suite. The saved 316-candidate audit reranks to 67 strict matches, so no secondary relaxation or expansion ran. The initial search's two-adult context and partial coverage remain distinct from the new one-adult guest-capacity criterion. No new candidate search was performed in this turn.

Reviewed source-path resolution, typed request party verification, listing/currency checks, conflicting-price handling, separate calendar displays and verified party amounts, selected-option explanation association, and exact stay totals. The raw one-adult canary verifies two BookIt stay-option totals but supplies no nightly amounts. Fixture-only positive-price tests establish behavior if real source amounts and party evidence become available; they do not represent live prices.

Reviewed file SHA-256:

- `compset/adaptive.py`: `af6ce8da1b34da2797e2b692d2f36a5aff38ac07cde3838df3ceaf285bde5932`.
- `compset/nightly_rows.py`: `4cd2e07b3d9ab3a29bc6de975f932b9e97fa391486311d2a696a454bef4e7938`.

## Live source observations and cache proof

Subject `1567889913136387224`, one adult, zero children/infants/pets, AED. Canary run `521a6b08734da5df84230398` observed 30 dates on `[2026-09-28, 2026-10-28)`: 8 available, 22 unavailable, zero priced. The separate 17–20 October stay returned exact BookIt totals AED 2264.65 non-refundable and AED 2488.50 refundable. Neither total was divided into nightly amounts. Actual BookIt locale en-IN is retained separately from requested locale en. Calendar requests did not establish a guest count.

The selected-competitor batch used one browser bootstrap, one reusable direct HTTP session and 67 serial calendar requests, at least three seconds apart. All 67 responses produced complete 30-date observations. Result: **2,010 rows, 1,242 available, 768 unavailable, zero unknown dates, zero calendar-display amounts and zero verified one-adult nightly amounts**. An unavailable night is not classified as booked. Complete calendar collection is not complete price collection.

Original batch report and combined CSV are preserved under `data/nightly-batches/2026-09-28-40beef015e564cc4/`. Per-listing sources, results and nightly artifacts remain in their run directories; SQLite contains derived `nightly_context` observations. These local evidence files are excluded from Git.

Personally ran the same selected job with `--request-budget 0` after completion. It validated and reused all 67 artifacts, reported complete calendar collection, **zero bootstrap visits and zero direct requests**, and retained `requested_party_prices_complete=false`. Missing prices did not trigger retries.

## Final executable verification

```text
.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 230 tests in 10.459s — OK

node --check compset/static/app.js
exit 0

docker compose -f routes/docker-compose.yml config --quiet
exit 0 (configuration validation only)

PRAGMA integrity_check
ok

git diff --check
exit 0 (line-ending conversion notices only)
```

The route reviewer separately personally passed 34 route tests, including the temporary SQLite upgrade proof. No public proxy has been fetched, validated or activated; no Docker build/start occurred. The shipped pool is empty and all live collection above used direct access.

After refreshing the existing dashboard tab, personally verified visible one-adult and 30-day defaults, Dubai start date 28 September, 316/67 candidate audit and explicit adaptive policy text. Historical two-adult portfolio observations remain labeled two-adult. Screenshot: `docs/screenshots/one-adult-window.png`. No collection was triggered through the UI. New nightly and proxy workflows are CLI tools, not additional dashboard job controls.

The previous dashboard-process restart attempt was rejected by automatic approval review with “blocked by policy.” No alternate stop/start was attempted. Static changes load after page refresh; saved server-level changes still require a permitted service restart. This does not change the separately executed CLI proof.

Order 005 implementation and local proof are complete. Operational gaps remain explicit: no live proxy validation, no verified nightly source prices, no exhaustive market/corporate coverage, and no new recurring scheduler.
