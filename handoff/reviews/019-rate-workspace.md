# Independent review 019 — rate-intelligence workspace

Date: 2026-09-28. Order: `handoff/orders/010-rate-intelligence-workspace.md`.
Reviewer: Codex subagent `/root/ota_review`, independent of the application implementers.
Workspace: `C:\Users\astha\CompSetStudio`.

**Result: implementation accepted on the frozen files below; live runtime activation is not accepted or claimed.** No unresolved correctness finding remains in the reviewed projection, HTTP route or client behavior. The reviewer edited only `tests/test_workspace_review.py` and this report. No collector, external site, credential, browser or persistent runtime was started by this review.

The main runtime on port 8765 still has the older route table. Root reported read-only confirmation of `/api/status` 200/idle and `/api/one-night` 200, while `/api/workspace` and `/rates-workspace.js` returned 404. Root's controlled restart was rejected by automatic approval review as **“blocked by policy”**, with no further reason supplied. The reviewer did not retry a restart, alternate port, browser surface or process workaround. The new legacy-app fallback explains that a restart is needed and leaves existing tabs reachable. This review proves the new implementation in isolated HTTP tests and Node DOM/model tests; it does not prove browser layout, Lighthouse account access or activation in the existing runtime.

## Scope and resolved findings

- Read-only public projection of the existing Aketa, Airbnb and BnBMe evidence; fixed-file `/api/workspace`; client filters, paging, details, CSV, profile and candidate views; default-tab integration and legacy reachability.
- Airbnb selected `rate_plan` and nested `rate_options` were initially lost. The projection now retains the actual selected Non-refundable AED 610.36 and Refundable AED 650.40 alternative, preserving selection and cancellation fields without substituting the alternative into the grid.
- Timestamp ordering initially compared strings. The implementation now compares aware UTC instants and retains the source timestamp text; a 12:00 +05:30 observation does not supersede a later 07:00 +00:00 observation.
- Saved one-night planned listing IDs now retain the full grid when current comp-set membership is absent or changed. Original two-adult discovery context is shown separately from the one-adult price context.
- Candidate UI mappings now use the actual distance, rejection, missing-field, host-count and operator fields rather than leaving those facts only in raw JSON.
- An independently reproduced typed negative with canonical hotel context but explicit legacy Agoda provider `27746358` initially marked canonical Agoda `110205` unavailable. The owner fixed negative validation across the top-level observation, requested context and observed context. Six independent mutation cases now reject those conflicts, while the real canonical negative remains valid.

The final suite ran after the negative-provider fix and UI freeze. Earlier runs overlapped a transient implementation edit and an outdated synthetic Google precision fixture; neither is represented as final proof. The independent Google fixture now uses `displayed_decimal`, matching the accepted Google display contract rather than inventing an exact supplier quote.

## Reviewer-executed proof

1. Command: `.venv\Scripts\python.exe -m unittest discover -s tests -q`

   Final captured output:

   ```text
   Ran 418 tests in 26.789s
   OK
   ```

   This includes the reviewer's **22** tests: five isolated HTTP tests, two Node-backed integration/model tests, and fifteen evidence-projection tests. They cover exact property/source/stay/party/currency/type isolation; zero, negative and nonfinite price rejection; missing and conflicting negative evidence; hotel-profile isolation; taxes/basis incompatibility; Google abbreviation and partner separation; Airbnb restrictions versus unavailability; instant-based freshness; planned denominators; selected and alternative plans; safe links, fields and source-file immutability.

2. Isolated HTTP tests instantiate `ThreadingHTTPServer(('127.0.0.1', 0), Handler)` with temporary data and shut it down after every test. GET is local and no-store, foreign Host/Origin is rejected, arbitrary file/query parameters cannot expose a sentinel, POST does not create a refresh job, malformed data remains visibly unknown, and same-path source revision changes invalidate the projection cache. Collector and subprocess calls are patched and asserted not called. No existing runtime is restarted.

3. Independently ran `node --test tests/test_rates_workspace.js` with `COMPSET_WORKSPACE_FIXTURE` pointing to a temporary UTF-8 JSON produced by `build_workspace(Path('data'))`. Result: **13 tests passed, zero failed/skipped, 567.5268 ms**. The temporary fixture was deleted by `TemporaryDirectory` cleanup. The test executes the actual workspace module, renders every section of both real datasets into a DOM stub, opens/closes details, and exports visible cells. It also checks paging, source/state/search filters, exact decimal display, formula-safe CSV, safe text and links, alternatives, candidate fields, membership conditions, profile distinctions, saved-only refresh, and error preservation.

4. The reviewer's Node VM test executes the actual `app.js`, checks IDs against `index.html`, verifies `rates-workspace.js` loads before `app.js`, confirms the new default mount and toggles all four main views. Existing comparison, portfolio and saved-price tabs remain reachable. Captured initialization requests are GETs only. A separate independent CSV test parses the generated CSV with Python's CSV reader and proves source/date-window/state filters, original guest context, unknown amount blanks, exact decimal preservation and spreadsheet formula neutralization.

5. `git diff --check` completed without whitespace errors. Git emitted only the existing Windows LF/CRLF conversion warnings. Source and evidence hashes below were recorded after the final suite. Test logs are the captured tool outputs summarized here; no additional persistent log files were created.

## Actual saved-data assertions

The reviewer independently projected and asserted the following, rather than copying summary counters from source files:

| Dataset | Planned cells | Quoted | Indicative | Unavailable | Restricted | Unknown | Offer rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aketa | 150 | 0 | 31 | 1 | 0 | 118 | 51 |
| Airbnb | 2,040 | 2 | 0 | 790 | 792 | 456 | 2 |

Aketa contains five sources and eight distinct audited profiles. Canonical Agoda has 14 offers on September 28–29 with lowest observed display INR 5,169; all 14 retain `taxes_included=false` and `fees_included=false`, and remain indicative. The single verified negative is Agoda September 29–30 for the recorded one-adult, one-room context. It is not whole-calendar closure or a booking claim. Google remains an indicative observation origin and its partner details do not replace the calendar display.

Airbnb retains 68 entities, 316 candidate records and the selected/non-selected rate options. Original candidate discovery used two adults; prices use the saved one-adult context. The 113-property BnBMe catalog remains separate from hotel rates and Airbnb identity matches. Every unknown, unavailable or restricted cell has a null amount. No market median, parity rank, booked occupancy, currency conversion or live availability inference is calculated.

The five source files were hashed before and after actual-data projection and were unchanged:

```text
5e8982e6f258f757126004270d03cb8bbe8c72d00b1ee7b9fee2ee97e68a7e0f  data/hotel-pipelines/latest.json
95810e543bb95493b0525ce867e31b5359c3022ee2d1fb3158a46d63594a9c38  data/hotels/aketa/profile-audit/profiles.json
e82f27ac594e533d782bed4059a91fe1c2365363e697e56ab220a8ea22fc1899  data/compset-latest.json
09ca9c6a202f65410f0fc81914d89a25094787e947cf7bfe080c9b80f8164a77  data/one-night-latest.json
c4ca8aa6a22de2221e25d5fcf92aed3cc2b3c8cb3da500107611635bbdd46e48  data/portfolio-latest.json
```

## Reviewed file hashes (SHA-256)

```text
f13220d4e3bebd897c57eaa0914e71eff8ff7f2fafb1ffe15c52cfdcedcbbd48  compset/workspace.py
f8364cfbdb26c92e8b0b46ca4f24dd5063646e0dce2af758c8d0445b085b0862  compset/server.py
5cdb76cb0bd45ca6dca08cf809f5d6c9d14043c808fe0d7b666726c58446958e  compset/static/rates-workspace.js
14ff8b76c3fc21521023691ad7576fea8cd4ab8d9b6d8b2e69a3d1ad83bfe999  compset/static/rates-workspace.css
31567ac086d265aa53b3a8de54661ab3a3502ab468b7b3d09a8b02040f1e9046  compset/static/index.html
14968a6e3d2ddf2344b6ca839adcaffa2cfd279c507222ee8d62d5c550e3e8c7  compset/static/app.js
e889eb8016225e601a2113c0bcfd84e562bf960ad664c74d0a2c2bcc3d76f892  compset/static/style.css
b2254dbcb00ba7a1579dd5bd2e37a3bc29bf93c3b7c95de8173ad9e0ec1516a5  tests/test_workspace.py
186328b848285a2a32ed739a4c6c8b72afd804d021cfdb8254707eef9f903958  tests/test_workspace_review.py
56dc82a51b8ec9b9d17a9ab6a88307aeca1db22bb8ce69cd610fb3b0e9f10af2  tests/test_rates_workspace.js
fbf638c2f18d71ea762355b0dc8f0bbbddd2bae130b87426de1ca259a366f68a  docs/rate-workspace-contract.md
51b90da983ba0e93eedb91250d7c7a512992c1e11b1dc2de339681ab7da60ca3  docs/rate-intelligence-workspace.md
```

Acceptance is limited to this source snapshot and the recorded evidence. Browser visual/accessibility behavior, newly collected OTA data and runtime activation require their own proof when available.
