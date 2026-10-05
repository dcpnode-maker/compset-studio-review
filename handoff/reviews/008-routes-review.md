# Order 005 independent routes review

Reviewer: Codex sub-agent `/root/scrapling_research`. Implementation owner: `/root/transport`. The reviewer did not implement `routes/`. Reviewer edits are limited to `tests/test_routes_review.py` and this record. Earlier reviewer's work on normalization, availability, batching and nightly artifacts is not covered by this independent source review.

Status: **accepted for the reviewed local route component**, with no open findings. All five findings below were repaired by the implementation owner and personally re-executed successfully by the reviewer. Tests use in-memory fakes, temporary SQLite databases and loopback-only fixtures. No public proxy list was fetched, no public proxy or target request was made, and Docker was neither built nor started.

## Findings

1. **P2 — manifest success and provenance are not strict.** `Pool.import_manifest` accepts `alive: "false"` and `alive: 1` as successful checks. It also accepts a route with empty source URLs or only an unrecognized source, silently persisting empty provenance. Malformed rows such as `null` abort the whole import before a later valid row. Require a typed successful result and retained recognized source evidence, rejecting malformed individual rows safely.
2. **P2 — CONNECT discards a valid delayed response after half-close.** `_tunnel` cancels both pipes when either finishes. The review fixture sends opaque request bytes, closes only the request direction, then supplies a delayed response. The response is discarded after the `200 Connection Established` header. Preserve the other direction until EOF or the existing bounded timeout, propagating half-close where supported.
3. **P2 — bind failure skips resource cleanup.** `main` opens the pool and HTTP client before `start_server`, but begins its cleanup block only after binding succeeds. A simulated address-in-use exception leaves both resources open. Cleanup must also cover startup failures.
4. **P3 — non-object control JSON is mislabeled as transport failure.** Posting JSON `[]` to `/_route/report` results in an attribute error and HTTP 502. Reject the malformed control input with 400 without modifying session or target state.
5. **P2 — HTTP response hop headers are incompletely removed.** `_http` strips the fixed hop-header list but forwards headers named by the upstream `Connection` header. The fixture `Connection: X-Route-Internal` plus `X-Route-Internal: hop-only` reaches the caller. Strip those nominated fields as well.

All findings were sent to the parent and implementation owner. The reviewer made no implementation changes. The final implementation requires typed successful checks with public-list or explicit operator-file provenance, tolerates malformed rows, drains CONNECT half-closes, cleans up failed startup, rejects non-object control JSON, and strips nominated response hop headers.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

- `.venv\Scripts\python.exe -m unittest tests.test_routes -v`: **17 tests passed**, 1.785 seconds. This establishes the implementer's current offline baseline; it does not establish working public routes.
- `.venv\Scripts\python.exe -m unittest tests.test_routes_review -v`: initial nine tests executed, five passed and four test cases failed (seven failed subcases/assertions), personally reproducing findings 1–4.
- `.venv\Scripts\python.exe -m unittest tests.test_routes_review.ManifestReviewTests.test_malformed_manifest_rows_are_rejected_without_hiding_valid_rows tests.test_routes_review.TransportLifecycleReviewTests.test_http_strips_response_connection_nominated_headers -v`: one import error and one failed assertion, personally reproducing the malformed-row portion of finding 1 and finding 5.

The independent tests also pass checks for an empty shipped pool, Compose's explicit `127.0.0.1:8080:8080` publication, caller report rejection on non-local Host, browser Origin, missing authentication and unknown session; duplicate/folded/oversized headers; mixed public/private DNS answers; exact target allowlist and ports; and one-shot recognized HTML challenge reporting without leaking request secrets.

- After the implementation owner's freeze, `.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_routes*.py' -v`: **32 tests passed in 3.573 seconds**, personally executed by the reviewer. All previously failing regressions now pass. The guard for `--container` outside Docker also rejects before opening the pool or binding, and local-mode startup is asserted to bind `127.0.0.1`.
- The parent additionally authorized an operator-supplied file mode during repair. The reviewer read the added implementation and personally executed the tests proving that this mode bypasses public-list fetching, retains the same verified-HTTPS probe and candidate budgets, rejects private/malformed endpoints, and exports a fixed source label, SHA-256 digest and byte count without the source's local path/name. Source type remains `operator_supplied`, never a residential/mobile assertion.
- The reviewer added two further independent tests: rejection of incomplete/ambiguous operator-file provenance, and an actual old-schema SQLite upgrade in a temporary directory. Reopening the upgraded database twice preserves the existing proxy fields, pinned session, halted status and cooldown; `PRAGMA integrity_check` returns `ok`. The added column initially contains `{}` for legacy rows, without inventing new provenance.
- Final `.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_routes*.py' -q`: **34 tests passed in 2.546 seconds** (20 implementation tests and 14 independent review tests), personally executed after those additions.

## Boundaries and limits

- Local mode binds `127.0.0.1`. Docker mode binds the container interface and the supplied Compose configuration publishes only host loopback. Container mode therefore depends on the supplied dedicated Docker network and publication configuration; the reviewer inspected those files but did not start Docker or verify runtime network isolation.
- Proxy endpoints must be literal globally routable IPv4 addresses. Exact target hostnames and ports are allowlisted, and the local DNS answer set must contain only global non-multicast addresses. The upstream HTTP proxy resolves the forwarded hostname itself; local DNS checking does not prove its independent DNS result or endpoint trustworthiness.
- CONNECT bytes remain opaque. The Requests wrapper sets `verify=True`, disables environment proxy inheritance and redirects, and has a bounded body/timeout. The proxy cannot independently verify a caller's tunneled TLS or detect a tunneled target block. Arbitrary clients must verify TLS and report blocks themselves; no such guarantee is claimed for non-reporting clients.
- The pool pins sessions, does not replace failed pinned routes, and keeps target blocks separate from proxy transport health. Target cooldown plus explicit manual session reset remains required after a reported block. Caller reports are local control, not a multi-user authentication boundary; session IDs are routing metadata with no password.
- A manifest's successful HTTPS httpbin probe establishes only that recorded probe. Route category stays `unknown`; residential/mobile, anonymity, a fixed egress IP, and Airbnb usability are unverified. The shipped route pool is empty.

## Reviewed hashes

SHA-256 at final personal execution:

| File | SHA-256 |
| --- | --- |
| `routes/airbnb_scraper.py` | `cfb1e210cb7dc58bb3e1242a28cadefa2536f953efe0def66d2b371ade11ad65` |
| `routes/kaggle_fetch_validate.py` | `42a54fe30f464111c84cff614fd3deef517c0923c938325b74136a58958ced89` |
| `routes/pool.py` | `51ed5106780823bdfb090e05f4743bca40e29d63ac638a4b8b9c049a44f4847a` |
| `routes/proxy_server.py` | `f92f09277c0a1bb451a0589a93ba72d99123b14993d03c0719480b9339a33dad` |
| `routes/Dockerfile` | `ec27d21f1607afae81462483cdaf074204169b111b899837046b1c04ce293f9c` |
| `routes/docker-compose.yml` | `eddb72232f4127e3c9c76eeb92da03df84b40861b8061d8407f45d962008ed1f` |
| `routes/requirements.txt` | `6cc2efb89df6dd8ee4cf0b37ecc0d2edd2ef5c1081bd6467058f5bbc43a9f08d` |
| `tests/test_routes_review.py` | `850b0ab47217d0613adfe1d2bdf0a2bae3ee0c19728f61759ee5088cf85acd2c` |
