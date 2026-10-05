# Order 005 independent nightly and workflow integration review

Reviewer: Codex sub-agent `/root/discovery`; implementation owner: root agent. Reviewed components: `compset/nightly.py`, new CLI branches in `compset/__main__.py`, one-adult/30-day default changes in `pipeline.py`, and the root-owned adaptive callback integration in `workflows.py`. The reviewer did not implement these changes and modified only independent regression files and this review record. The reviewer implemented `adaptive.py`; acceptance here does **not** independently review that pure module. Parent owns its independent adaptive review. The separate nightly-row builder was inspected for integration contracts, without claiming a complete independent source review of its price semantics.

All reviewer proofs are offline. Temporary snapshots, raw JSON fixtures, mocked transports and temporary SQLite databases were used. No target HTTP requests, proxy validation, Yellow edits or external writes occurred.

Status: **accepted for the reviewed root orchestration scope** on 2026-09-28. All seven findings below are resolved and reviewer-executed regressions pass. The earlier full-suite route failure snapshot below is historical; dedicated route acceptance and repaired-code verification are tracked separately in `008-routes-review.md`.

## Findings and corrections

1. Party/window validation originally accepted `adults=True`, `adults=1.0`, `days=30.0` and Boolean zero-party values, then silently replaced them with integer defaults. The reviewer reproduced these inputs. Owner now requires exact integer scalars; reviewer-executed strict-scalar cases pass. Explicit two-adult historical contexts retain two adults.
2. A checkpoint decoded as a JSON array raised `AttributeError`; numeric selected IDs were retained as integers while completion IDs were strings; duplicate/outside-selection cached records were not guarded. Owner added mapping/list guards, canonical string IDs, selected membership and deduplication. Reviewer regressions now pass without starting a bootstrap.
3. Completed cache metadata did not verify the actual saved artifact. Owner added run-ID/path/party/window/coverage checks and guards for missing rows, malformed row count/identity/dates, and the artifact's own observation age. Reviewer proves a valid cache is reused, but absent artifacts, missing rows, stale artifact timestamps, wrong run IDs, old checkpoint timestamps and changed parser fingerprints are not reused.
4. Orchestration initially used price/availability aggregate names different from `nightly_rows.py`. Builder/owner aligned the contract. A reviewer-provided returned calendar with explicit observed one-adult request context and 30 returned prices now counts 30 verified nightly rows; a requested context alone never supplied those prices. The normal fixture has no returned prices and correctly reports zero.
5. **Resolved — cached aggregate falsely claimed price completeness.** The reviewer preserved a real temporary artifact whose 30 saved `nightly_amount_for_requested_party` values are all null, changed only `coverage.verified_nightly_price_days` to30, and resumed with request budget0. Before correction the job incorrectly reported 30 verified rows and complete requested-party prices. Root now derives cached coverage from actual rows with source evidence, explicit Boolean guest verification and positive returned party amounts. The independent regression now reports zero verified prices and incomplete requested-party price coverage.
6. **Resolved — the additional detail budget reset per radius.** Two radius transitions returned 201 new IDs each; before correction the reviewer counted **400** detail calls despite an intended 200-read total. Root now holds `new_detail_remaining=200` outside the callback and decrements it across transitions. The independent regression personally verifies only 200 additional detail reads across both transitions and zero remaining budget.
7. **Resolved — expanded progress used the initial candidate count.** Root now reports the final ranked audit count. The independent shared-budget regression verifies 402 audited candidates in final progress. Initial enrichment concurrency was raised against Order005's canary policy; the owner clarified that its two-worker detail lane predates the order and was allowed after a completed one-adult live subject canary. That live canary and the subsequent serial 67-listing calendar batch are owner-reported context, not reviewer-executed network proof.

## Reviewer proof

Working directory: `C:\Users\astha\CompSetStudio`.

Reviewer-created `tests/test_nightly_review.py` exercises:

- Exact one-adult party scalars and explicit historical two-adult defaults.
- Malformed checkpoints, duplicate/string/numeric IDs, actual artifact presence and freshness, complete row identities/dates, and parser-fingerprint invalidation.
- Cooperative pause set during spacing: one completed request, no second HTTP start, pause flag retained.
- HTTP500 and GraphQL errors: stop at the first competitor and mark the observation incomplete.
- Temporary SQLite round trip: the entire previous two-adult `result_json`, its 31 observations and `latest.json` remain unchanged; one-adult subject/competitor rows append; `PRAGMA integrity_check` returns `ok`.
- A positively priced synthetic calendar with explicit observed party provenance, actual builder aggregate keys and native AED values, plus a cache metadata conflict with missing row prices.
- Actual CLI defaults and forwarding: default one adult, explicit two adults preserved, and zero request budget forwarded without bootstrap.
- Root callback total search-budget subtraction/exhaustion, total additional detail budget, final progress count and no later detail/search read after an enrichment access limit.

The updated prior runtime regression patches the imported `compset.adaptive.rank_candidates` binding with a complete summary fixture, preserving its original assertion that subject geography and actual guest floor reach ranking. This is a test binding adaptation to root integration, not a runtime change.

Initial independent command `.venv\Scripts\python.exe -m unittest tests.test_nightly_review tests.test_runtime_review -v` executed 21 tests in3.578s: all 10 nightly tests and 8 prior runtime tests passed; two callback guard cases passed; the total detail-budget case failed400 versus200. A later individual cache-price conflict test personally failed30 versus0. Reviewer fixed a test-only Windows temporary cleanup issue by using `contextlib.closing` on its SQLite reader.

## Scope limits

Complete calendar observations are distinct from complete requested-party prices. A successful calendar collection can retain zero verified nightly amounts. Existing two-adult website/calendar observations are never relabeled as one-adult prices. Full market/corporate inventory coverage is not asserted. Bootstrap browser/replay costs remain separately reported from the direct competitor request budget. Parent owns live canary, route/provider validation, UI integration and independent review of the reviewer's adaptive module.

## Final executable proof and source identity

Personally executed after the owner's final corrections:

```text
.venv\Scripts\python.exe -m unittest tests.test_nightly_review tests.test_runtime_review -v
Ran 22 tests in 4.310s — OK

.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 224 tests in 10.709s — FAILED (failures=8, errors=1)
```

The full-suite failures were confined to `tests/test_routes_review.py`: malformed manifest rows raised an exception; non-Boolean success and missing/unknown source provenance were accepted; non-object report JSON returned502 rather than400; CONNECT half-close dropped a delayed upstream response; a response connection-nominated header leaked; bind failure did not close the client/database. Several manifest subcases account for the eight failure total. These route files were neither implemented nor changed by this reviewer.

After this snapshot, the parent reported that the dedicated independent route reviewer personally passed 32 tests after author repairs, with final acceptance to be recorded in `008-routes-review.md`. That repaired-route result supersedes this historical route-failure snapshot for route acceptance; it was not personally executed by this reviewer. Parent's repaired-code full-suite rerun was still in progress when this record froze. This record makes no claim that its historical full-suite command passed or that a final full project suite result was personally verified here.

Reviewed branch: `codex/one-adult-nightly-coverage`; Git HEAD: `c9683850e299de1f9a06bbef778410b35d744790`. Reviewed changes are dirty relative to that HEAD; SHA-256 identities, captured at `2026-09-28T02:47:00.276115+00:00`, identify the actual files tested:

| File | SHA-256 |
| --- | --- |
| `compset/nightly.py` | `43d84bbf98fcee6e82276397eb4bfe86b2b9bffa5fa4302b8bf4e13b280c69a0` |
| `compset/__main__.py` | `628c2c5c7defc903f047572c09dbc77a53f3cd8f6222108c97db61baf9189f09` |
| `compset/pipeline.py` | `f05361c5cb99c9ad937e3c38b6205ac351a5e22300c8cc89b18c769899312864` |
| `compset/workflows.py` | `cab961c4051dd033c3d859804ccad1dc7b8cf0920eaba610501e94b3cfea85cf` |
| `tests/test_nightly_review.py` | `12cb49f7ed2bb02d3c1b73c786c175878e2ef0981c8fcd2eb1d07a97c613ff0b` |
| `tests/test_runtime_review.py` | `891e90f6acd88b5a953c2b29faf06da60f50938c8465ff076e8684e2e96f17aa` |

No residual actionable defect was found in the reviewed orchestration scope after these corrections. Live upstream price availability, collector route safety and the separately implemented pure adaptive runner require their own proofs; they are not established by these offline regression results.
