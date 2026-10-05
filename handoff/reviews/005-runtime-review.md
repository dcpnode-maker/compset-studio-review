# Order 004 independent runtime review

Reviewer: Codex sub-agent `/root/discovery`. Implementation owner: root agent. The reviewer did not implement the reviewed runtime components and changed only this review record and the authorized independent regression file `tests/test_runtime_review.py`. The reviewer previously implemented `portfolio.py` and `discovery.py`; executing their tests here does not constitute independent source review of those components.

Scope: `compset/health.py`, `refresh.py`, `server.py`, the atomic JSON writer in `pipeline.py`, the parsed listing cache in `workflows.py`, and the source-container reference change in `profile.py`. Inventory monetary/identity normalization was independently reviewed in `004-inventory-review.md`. No external requests or collection jobs were started for this review. All mutation probes use temporary directories and patched transports.

Status: **accepted for the reviewed runtime components**, with no open findings. The implementation owner corrected all five findings and the remaining malformed-JSON cache subcase. The reviewer personally re-executed the regressions and the full suite successfully on the final source identified below.

## Findings

1. **P1 — an accepted pause can be erased at worker startup.** `refresh_inventory` unconditionally deletes `pause-inventory.flag`. The server accepts `/api/inventory-refresh` and launches the worker asynchronously, so a subsequent accepted pause arriving before the child enters `refresh_inventory` is removed. The reviewer placed the flag before worker entry and patched collection/import: the collector saw `flag.exists() == False` and the refresh returned `complete`. Clear the previous job's flag while accepting a new start under the server lock; preserve a subsequent pause in the child. A cooperative pause may permit the already-running HTTP request to finish, but must prevent new starts afterward.

2. **P2 — a host collection access-limit stop is reported as complete.** `refresh_inventory` discards the return from `collect_host_inventory`. With a successful website batch and a host result `report.state='stopped', stop_reason='access_or_rate_limit'`, the independently executed refresh returned `state='complete'`. Retain that report and propagate its stop state while still importing the saved evidence.

3. **P2 — a structurally invalid diagnostic baseline aborts import.** `observe_contracts` catches invalid JSON but assumes successfully decoded JSON and its `contracts` member are mappings. Both `schema-health.json` containing `[]` and `{"contracts": []}` raised `AttributeError`. Because inventory import invokes this diagnostic first, a local diagnostic file can block persistence of otherwise usable source observations. Validate decoded shape and each registry entry; report a baseline warning and rebuild diagnostics without discarding source evidence.

4. **P2 — filesystem modification time is treated as observation freshness.** The listing cache uses raw file mtime for its six-hour window. The reviewer wrote an observation dated `2020-01-01T00:00:00+00:00` into a newly modified raw cache and a matching parsed cache: `listing_detail` returned that old observation with zero HTTP calls. Check `observed_at` age, retaining mtime only for parsed-cache revision matching. Malformed/materially future timestamps must not silently qualify as current observations.

5. **P2 — malformed parsed-cache records abort discovery.** A parsed cache with matching parser hash/source mtime but no `listing` key raises `KeyError`; a nonmapping `listing` is likewise not validated before returning. A parsed cache is expendable: validate its wrapper/listing and reparse usable raw evidence on failure rather than aborting a discovery/host job.

Initial owner corrections resolved all original reproduced cases. Reviewer-added `tests/test_runtime_review.py` then found one remaining finding-5 subcase: malformed parsed JSON skipped the otherwise fresh raw cache because both reads shared a `try` block, initiating an unnecessary HTTP request. The reviewer reported this failing assertion to the owner for a narrow cache-read correction.

## Reviewer-executed evidence

Working directory: `C:\Users\astha\CompSetStudio`.

- `.venv\Scripts\python.exe -m unittest discover -s tests -v`: passed.
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`: **133 tests passed in 3.910 seconds**, exit 0. The existing suite does not cover all five failure cases above; passing it did not override the reproduced failures.
- Offline Python commands supplied through a PowerShell here-string to `.venv\Scripts\python.exe -` personally reproduced findings 1–5 using `tempfile.TemporaryDirectory` and `unittest.mock.patch`. Transports, host collection, and inventory import were patched; no real source or production checkpoint was changed.
- Projection proof called `portfolio_response(path, path.stat().st_mtime_ns)` before/after two atomic file revisions. It asserted the original full JSON remained unchanged, quotes and public `attributes`/`detail_attributes` survived projection, large calendar/detail/profile containers were omitted only from the UI response, and a new mtime returned the new snapshot. All assertions passed.
- Atomic writer proof patched `Path.replace` to raise two `PermissionError`s, then used the real replace on the third attempt. The final destination was complete parseable JSON; the prior contents were never partially overwritten. All assertions passed.
- `profile.py` source review confirms the excluded large evidence containers remain on the copied top-level listing and are referenced by name/count from `profile.source_containers`. The no-loss profile regression passed in the full suite. Original source attributes/calendar remain available in full JSON/SQLite.
- Actual retained website source was loaded offline and passed to `inventory_health(source, temporary_directory)`: **12 semantic alerts, all `non_success_response`**, corresponding to preserved HTTP500 quote failures. `get-charges-breakup/sold_out` and priced `get-charges-breakup` were separate expected contracts; no automatic semantic repair was enabled. The source file hash before/after was identical: `1e6bdc98ab0306c1c4cb9e85621e623ef68cfc21d9ffa61dbdf0d7dcd55b9aab`.

The reviewed diagnostics do not manufacture prices, convert SOLD_OUT stays into unavailable calendar nights, reinterpret missing inventory placeholders as free nights, or rewrite raw source observations. Source records with missing inventory IDs retain the separately reviewed inventory normalizer's explicit unknown handling. No claim is made that all 41,245 returned date cells have real rates; 8,604 source placeholders remain unknown.

## Reviewed source identity

`git rev-parse HEAD` failed because this standalone repository has no initial commit. There is no commit SHA to report. First captured file SHA256 values during review/owner corrections:

| File | SHA256 |
| --- | --- |
| `compset/health.py` | `09b42d8c3e0f6236b0fa6bf127fe4fddb3e412222962ae9c114e85b5a80cdf92` |
| `compset/refresh.py` | `a6bd729745abe323eb065067dcf3d7da17730910ac65267df4d9c1b5fc269b75` |
| `compset/server.py` | `bae44fdf2d6ed6966a02fb9d5b86a931e7870a39192eabb2bd03eaed0d943b6b` |
| `compset/pipeline.py` | `a6b6ff6e09f972b15f11b5676ff78f1fd2d359e6f82c017b45b5f6c813c02e86` |
| `compset/workflows.py` | `c9448f8b6aedaff588f289e84a6bfd7b088c206abb99e02b46628fa48c28a10f` |
| `compset/profile.py` | `bc8af1930914b8e7ec34d00dbf14a85a032d1dbcfa8cf4aa84a987b8850967a0` |

## Limits

Live browser/dashboard interaction remains the implementation owner's integration proof. This review did not initiate network collection, assert corporate inventory completeness, review its own collectors independently, or change runtime implementation. Runtime acceptance applies to the final hashes and personally executed regression results below.

## Final reviewer acceptance

Final proof captured at `2026-09-28T00:31:20.183621+00:00` (UTC). Commands personally executed after the last owner correction:

1. `.venv\Scripts\python.exe -m unittest tests.test_runtime_review -v`: **8 tests passed in 2.123 seconds**, exit 0. The malformed parsed JSON subcase now reparses fresh raw evidence with zero HTTP calls. Missing/nonmapping/wrong-ID parsed records also fall back safely. Old, malformed, absent and one-day-future observation timestamps no longer pass the freshness check merely because file mtime is current.
2. `.venv\Scripts\python.exe -m unittest discover -s tests -q`: **141 tests passed in 4.885 seconds**, exit 0.
3. Source inspection confirmed separate parsed/raw cache `try` blocks, pause clearing only on an accepted start under the server lock, host stop propagation, diagnostic mapping/entry guards, and observation-age freshness checks.

The eight reviewer-written regressions independently execute the real loopback handler for accepted start/pause/duplicate-start ordering; refresh state propagation with evidence import; malformed diagnostic recovery without response mutation; cache age and parsed fallback; projection preservation/invalidation; atomic Windows read-lock retries; and non-Dubai subject location plus actual guest-capacity floor propagation. Temporary data and mocked network transports keep the proofs bounded and offline.

Exact accepted implementation/test SHA256 values:

| File | Final SHA256 |
| --- | --- |
| `compset/health.py` | `09b42d8c3e0f6236b0fa6bf127fe4fddb3e412222962ae9c114e85b5a80cdf92` |
| `compset/refresh.py` | `a6bd729745abe323eb065067dcf3d7da17730910ac65267df4d9c1b5fc269b75` |
| `compset/server.py` | `bae44fdf2d6ed6966a02fb9d5b86a931e7870a39192eabb2bd03eaed0d943b6b` |
| `compset/pipeline.py` | `a6b6ff6e09f972b15f11b5676ff78f1fd2d359e6f82c017b45b5f6c813c02e86` |
| `compset/workflows.py` | `25eedcd4d54199a0f52206f3a116cbf0899d734692f759450f2b402ca2f465b1` |
| `compset/profile.py` | `bc8af1930914b8e7ec34d00dbf14a85a032d1dbcfa8cf4aa84a987b8850967a0` |
| `tests/test_runtime_review.py` | `60b55fdc7f7d342a327bd28241b3c39db3f4dcaffe379eadb5d2e4747bb1df2e` |

`git rev-parse --verify HEAD` still reported no revision at final review. Acceptance therefore identifies the exact source files by SHA256 rather than inventing a commit SHA. No open findings remain within this review's scope.

### Deterministic projection revision regression amendment

The implementation owner's later full-suite execution exposed filesystem timestamp granularity: two quick temporary-file replacements occasionally had the same `st_mtime_ns`. The reviewer changed only the projection regression to set an explicit one-second-distinct nanosecond revision with `os.utime(ns=...)` before asserting cache invalidation. It still verifies that the original revision returns snapshot one and the explicitly changed revision returns snapshot two. No sleep or wall-clock timing dependency was introduced; runtime behavior was unchanged.

At `2026-09-28T00:40:44.101186+00:00` (UTC), the reviewer personally executed:

- `.venv\Scripts\python.exe -m unittest tests.test_runtime_review -v`: **8 tests passed in 1.534 seconds**, exit 0.
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`: **153 tests passed in 4.581 seconds**, exit 0.

The current regression-file SHA256 is reflected in the final table above. The previous regression-file SHA256 before this deterministic test-only correction was `01ca09e9779737eed020c33113e73ba13292a0f6eb168e206740f455506fd639`. Review acceptance remains valid for the reviewed runtime components. Running newer tests does not extend this review's source-inspection scope. No commit existed at this amendment.
