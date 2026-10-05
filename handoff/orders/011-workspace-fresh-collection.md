# Order 011: dashboard fresh-data collection

User requests a Lighthouse-like button that actually fetches fresh data. Extend standalone CompSet Studio only. The existing server restart and browser-policy denials remain binding: do not retry or work around them. Implement and verify source code with isolated HTTP, mocked transports and Node tests; do not initiate an unrequested live batch while building the button.

## Scope and ownership

- Backend agent: new `compset/workspace_jobs.py`, `compset/__main__.py`, minimal opt-in freshness/resume changes in `hotel_jobs.py`, `nightly.py`, `one_night.py`, focused new tests `tests/test_workspace_jobs.py`. Own fresh collection API contract additions in `docs/workspace-collection-contract.md` after coordination.
- UI agent: `compset/static/rates-workspace.js`, `.css`, and `tests/test_rates_workspace.js`. Real Fetch fresh data, bounded job status, cooperative pause/resume, saved evidence reload after completion, and honest dataset coverage notes. No server or collector edits.
- Root: docs/README/architecture/order, `server.py` route/lease integration (explicitly handed off by backend agent), `tests/test_server.py` fixture isolation if required, `static/app.js` status integration, coordination and verification. The legacy shell accepts partial/interrupted states and exposes an optional `CompSetCollectionStatus(job)` callback to synchronize the header and legacy controls with workspace collection. No overlapping implementation edits.
- Independent reviewer: `tests/test_workspace_collection_review.py`, `handoff/reviews/020-workspace-collection.md`; personally execute proof and inspect job concurrency, context, pause, freshness and negative-state semantics.

## Required behavior

Fetch collects the selected dataset's next 30 local dates with the supported one-adult context. Aketa retains one room, no children and INR. Airbnb retains the saved subject/selected set and its source currency; it refreshes calendars before bounded one-night quotes. View/search filters do not silently alter collection membership or party settings. Changing the viewed dataset must not pause, retarget or duplicate an active job.

One job at a time across existing collection controls and the new button. Explicit finite budgets, at least three seconds between starts, checkpoints, cooperative pause and resumable work. Fresh mode must actually request eligible current observations rather than silently serving all positive cache entries. Resume may reuse validated fresh observations. Neither mode bypasses access challenges or active source cooldowns; malformed responses and blocks remain unknown. Preserve history and source timestamps. Completed process, completed budget and complete price coverage are separate states.

GET reads never collect. Start and pause use same-origin JSON POST plus existing dashboard header, fixed supported datasets, validated job identity, no client-supplied commands/paths/endpoints. Status survives page reload, reports stopped/partial/failed accurately, and cannot show a previous job's progress as the current job. No credentials, spending, bookings, new database schema, recurring automation or server restart endpoint.

Current coverage must be clear: 113 returned BnBMe public properties, 60 unlinked Airbnb records, one saved Dubai subject with 67 selected competitors, and Aketa source rates with no hotel competitor set. Full BnBMe corporate inventory and per-property compsets have not been established.

## Delivery — 28 September 2026

Implemented the explicit Fetch fresh data, Pause collection and Resume collection workflow, with a separate read-only Reload saved data action. Collection membership and stay context are frozen per job; shared leases prevent overlapping legacy and workspace collectors. Durable checkpoints, finite budgets, source cooldowns, pacing, report backups and explicit partial/unknown states preserve honest results across long sessions. A fresh source read receives its actual observation timestamp, while reused evidence keeps its original timestamp.

Independent acceptance is recorded in `handoff/reviews/020-workspace-collection.md`. The reviewer personally executed the final full Python suite after the last source change: **456 tests passed in 41.474 seconds**; the affected suite passed 57 tests, including 23 independent lifecycle/transport/integration tests. The reviewer also ran **25 Node checks** against the actual saved projection, with no failures or skips. Root's seven legacy HTTP checks and 25 actual-data Node checks passed during integration. `git diff --check` passed. No live source collection was run for this delivery; the recorded saved-evidence hashes remain unchanged.

The code is accepted; activation on the existing server remains pending. Read-only checks returned 404 for `/api/workspace` and `/api/workspace/job`, while the old `/api/status` remained available and idle. The earlier automatic approval review rejected the persistent server restart as "blocked by policy", without a more specific reason. No restart, alternate runtime or browser workaround was attempted. Local HTTP and Node proof does not establish browser visual QA or a successful live collection batch.

Portfolio and competitor coverage remains incomplete: BnBMe has 113 discovered public properties, 60 Airbnb records without verified direct-site identity links, and a saved compset for one Dubai subject only. Aketa has 51 offer observations across eight audited profiles; 118 of 150 source/date cells remain unknown, and no competitor-hotel dataset has been collected. The new controls refresh supported saved datasets and do not create the missing compsets.
