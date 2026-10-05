# Independent review 020 — fresh-data collection controls

Date: 2026-09-28. Order: `handoff/orders/011-workspace-fresh-collection.md`.
Reviewer: Codex subagent `/root/ota_review`, independent of the application implementers.
Workspace: `C:\Users\astha\CompSetStudio`.

**Result: accepted implementation on the frozen source hashes below. Runtime activation and a live collection batch are not claimed.** No unresolved correctness finding remains in this review's scope. The reviewer edited only `tests/test_workspace_collection_review.py` and this report. All collection transports and worker process launches exercised here were mocked; HTTP tests used temporary data and short-lived loopback test servers. No browser, persistent service restart, credential access or external source request was attempted.

The earlier automatic approval rejection of the main runtime restart remains binding. Root reported that the existing service's new APIs still return 404. No alternate process, port or browser workaround was attempted. The UI explains a missing updated service rather than reporting a successful fetch. Source-code acceptance is distinct from activation in the current app and from proof that every OTA will return a usable live result.

## Reviewed behavior

- Explicit fresh collection and separate saved-data reload; guarded JSON POST starts and identity-scoped pause; GET never starts or resumes collection.
- Fixed Aketa/Airbnb dataset planning, finite budgets, frozen one-adult context and cohort, shared durable legacy/workspace lease, single worker identity, source cooldowns, three-second pacing and cooperative pause.
- Current job status and progress, partial/stopped/interrupted handling, report backups and existing append-only source history.
- Client polling and dataset switching without retargeting the active job; no automatic POST or source retry; truthful coverage and source timestamps.

## Findings resolved before acceptance

1. **Resume membership could silently change.** The first implementation replanned from the current saved comp set. It now requires a prior resumable job, copies that job's frozen context and selection into a new identity, and rejects an expired date window or missing plan. The independent test modifies both current membership and currency after a partial job and proves Resume retains the original cohort and AED context.
2. **New subject calendars could be ignored.** The calendar stage now carries an explicit `subject_record` into quote preflight, ahead of older `latest.json` subject evidence. A newly proven calendar block suppresses quote bootstrap even when the legacy subject report still permits the stay.
3. **Long-session source timestamps were wrong.** A new subject bootstrap on a seven-hour-old same-day resume initially retained the original job timestamp. The independent regression observed an age of approximately 25,200 seconds on that new read. The narrow fix stamps the actual bootstrap start; frozen dates and guests remain unchanged, cached-only paths retain their original timestamps, and quote planning accepts the fresh calendar.
4. **Inter-phase pacing and pause required a guard.** Successful calendar collection now waits at least three seconds before the quote phase and checks pause/deadline again. The independent test requests pause during that wait and proves only a zero-network quote checkpoint is permitted.
5. **Legacy cache/pause behavior regressed during implementation.** Stricter subject bootstrap and initial request spacing are now opt-in for the workspace/fresh flow. Existing legacy cache completion is preserved. The independent test separately proves that a workspace resume with a missing subject record still bootstraps that subject, so compatibility does not weaken the new flow.

The early `fresh` boolean/helper naming collision was also removed; executable cache-resume proof confirms the quote freshness helper remains callable. Prior full-suite results before these fixes are superseded by the final results below.

## Reviewer-executed proof

Final affected command, run after the timestamp correction:

```text
.venv\Scripts\python.exe -m unittest tests.test_nightly tests.test_nightly_review tests.test_workspace_jobs tests.test_workspace_collection_review -q
Ran 57 tests in 17.376s
OK
```

Final full command, started after the last source freeze:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 456 tests in 41.474s
OK
```

The reviewer's **23 tests** comprise eight HTTP/launch tests, nine job coordination tests, five collector-flow tests and one Node-backed legacy-app integration test. In particular:

- Real isolated HTTP requests prove one accepted worker, duplicate/legacy-start rejection, correct pause identity, old `progress.json` isolation, no-store and local-origin guards, and rejection of client-supplied commands, paths, sources, filters, guest context and budgets.
- Thread startup, subprocess launch and legacy preparation failures release their reservations and report failure. Two concurrent reservations produce one winner. A live lease is never reclaimed or stopped; a dead worker is reported interrupted. A second worker cannot execute the same job.
- Fresh rechecks healthy cached prices and verified negative inventory; Resume reparses validated raw quotes. Existing raw files and SQLite observations remain present. Recent source failure prevents transport despite fresh mode.
- A stopped calendar stage can invoke only a zero-network quote checkpoint. Pause during the calendar-to-quote wait also prevents quote transport. The current job receives only its own progress callbacks; a prior report's counts do not become new-job progress.
- Legacy controls accept partial/interrupted status without a connection error. Active workspace collection disables legacy subject/inventory starts and legacy inventory pause. The tested interactions issue no unauthorized POST.

The reviewer also personally executed `node --test tests/test_rates_workspace.js` with `COMPSET_WORKSPACE_FIXTURE` pointing to a temporary UTF-8 projection of actual saved data: **25 tests passed, zero failed/skipped, 667.0437 ms**. These client files were unchanged through final acceptance. The tests exercise actual click handlers with mocked HTTP: GET-only mount/reload, one guarded fresh POST, three-second polling, stale/foreign response rejection, dataset-pinned pause/resume, legacy busy preflight, terminal saved-data reload, filter/drawer preservation, explicit errors and no automatic retries. The actual projection renders both datasets and all sections and exports the visible cells. The temporary projection was removed when its temporary directory closed.

`git diff --check` passed; only normal Windows LF/CRLF conversion warnings were emitted. Logs are captured tool output recorded here; no additional persistent test log files were created. Tests did not alter the five actual evidence files listed below.

## Coverage and delivery limits

This feature collects the supported saved datasets. It does not establish compsets for every BnBMe property or discover Aketa competitor hotels. The tested actual projection still contains:

| Evidence | Current saved coverage |
| --- | --- |
| BnBMe catalog | 113 returned public properties; 60 Airbnb records without a verified portfolio link; complete corporate inventory not established |
| Dubai Airbnb | One subject and 67 selected competitors; 2,040 planned date cells: 2 quoted, 790 unavailable, 792 restricted, 456 unknown |
| Aketa | Five observation sources, eight profiles, no competitor hotels; 150 cells: 31 indicative, one contextual unavailable, 118 unknown; 51 offer rows |

Worker completion, exhausted budget and complete price coverage remain separate. Unknown prices do not become zero or unavailable; calendar restrictions do not establish bookings. Refreshing saved files or finishing a job does not replace source observation timestamps with a live-price claim. No new live batch was run to expand these counts during review.

Actual source hashes, unchanged before/after the review checks:

```text
5e8982e6f258f757126004270d03cb8bbe8c72d00b1ee7b9fee2ee97e68a7e0f  data/hotel-pipelines/latest.json
e82f27ac594e533d782bed4059a91fe1c2365363e697e56ab220a8ea22fc1899  data/compset-latest.json
09ca9c6a202f65410f0fc81914d89a25094787e947cf7bfe080c9b80f8164a77  data/one-night-latest.json
c4ca8aa6a22de2221e25d5fcf92aed3cc2b3c8cb3da500107611635bbdd46e48  data/portfolio-latest.json
6382142e013b440f8057efb8d9091ed61059c14c26dbd9628a645d450daf92a4  data/nightly-monitoring-latest.json
```

## Reviewed file hashes (SHA-256)

```text
c8d71e304dd23379e59714f0a0ca89fe3a657ce97190b70e3c1cb4e812adba59  compset/workspace_jobs.py
1469475f1a650f09dbd8566832843062bda3689e4794902abe94b95f76dda407  compset/server.py
6da728542fc81a4c7edf0eb458294984fca52e249f8120389b2d8b1ce546d587  compset/__main__.py
27e1158d7cb988d807737e470351323062d96c6fb0eff5846a02a6282b7beb13  compset/hotel_jobs.py
0923020ff5423fe1ade1f6ea5d8cc78a5665fe36e5574de21a82fb622e01b4ea  compset/nightly.py
f4175c0fb9475ada0b25b040a0f3c7a746912f61702659e8d69e9683bdb70e1c  compset/one_night.py
1b15790685ff061af45d4b412c244be4b9ce653f5c63e1e4e9a848eec228791c  compset/static/app.js
d6cf56e5eec820d84528198653a577c4ba8f1b12ab0e1fc45a795e5f66ed1638  compset/static/rates-workspace.js
2d95124ebba2154b7ec331911d07906a0910098b5395557eeb6e078820852795  compset/static/rates-workspace.css
0c9fa2e7b839c2a90080edb730881a7f554366e91817fa4536967a001271c5da  tests/test_workspace_jobs.py
0fab59bfd75b54ae9f38b959f7d2026d7d2f01568aa5d1cca3d018f67e1ae8d2  tests/test_workspace_collection_review.py
8c9a696afdd702c684c927a3f21f1db1a02eab24084a2a80d9eb76d55933d2e8  tests/test_rates_workspace.js
56433ed0dc659f35fe9216e8b47a5b0b12a16a2abfcd3d88b10f936ba7f03e64  tests/test_server.py
a5f986be0af008200f771682ccf350891d321e60b5b35b19102b47f9d381275f  docs/workspace-collection-contract.md
```

Acceptance is limited to these files and proofs. Existing runtime activation, real browser behavior and a live end-to-end fresh collection still require separate verification when permitted.
