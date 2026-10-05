# Order 008 independent hotel pipeline review

Reviewer: Codex sub-agent `/root/ota_review`. Implementation owners: root (registry, contracts, SQLite, job orchestration, CLI and UI), `/root/ota_booking_expedia` (Booking/Expedia), and `/root/ota_mmt_agoda` (MakeMyTrip/Agoda). The reviewer edited only `tests/test_hotel_portfolio_review.py` and this review. No production code, live source data, browser, external request, process launch or process restart was performed by this reviewer. HTTP checks below were reads of the existing loopback dashboard.

**Accepted at the source and evidence hashes below. No open code finding remains.** This accepts the bounded Aketa implementation and its explicit partial results; it does not claim working exact-price access to every OTA or a complete 30-day direct-OTA collection.

## Findings and repairs verified

- Initial contract inspection identified conflicting row identities and requested contexts being overwritten and failed observations potentially retaining prices. The owner added explicit rejection. Reviewer-created mutation tests now prove typed party, hotel, source, channel and currency isolation without modifying inputs.
- A personally reproduced budget failure gave all four canary visits to MakeMyTrip. The owner changed scheduling to visit each source once before additional dates. The independent four-source regression now passes.
- Personally reproduced abbreviated/approximate direct amounts were accepted as exact quotes. Exact quotes now require a positive exact amount and explicit exact precision. Valid Agoda integer displays remain separately classified as indicative, with verified stay context and their price basis.
- Personally reproduced parser `AttributeError` aborted unrelated sources. Ordinary parser exceptions and malformed non-object raw captures now produce isolated unknown interpretations while retaining raw evidence. Reviewer tests verify continuation, complete unknown coverage and persisted failed raw captures.
- Agoda initially rejected a valid one-adult result when an earlier two-adult request used the same dates. The parser now selects the exact actual request context. Contradictory property-level sold-out flags with priced rooms are quarantined. Both repairs were personally checked against copies of actual captured evidence, as well as executed owner regressions.
- The first packaged Agoda capture exposed optional `isFit` and child-promotion differences. Parsing now requires the actual one-adult/one-room offer and the matching request, returned form and response; it preserves the separate child promotion. The reviewer independently reparsed the unchanged packaged capture successfully.
- The UI initially used the older Google-only completion state for the partial multi-source report. It now displays the current pipeline state and time, per-source observations and all unknown source/date cells. Reviewer execution of the actual render function confirms the correction.
- A later owner-executed generic job captured an empty DOM during navigation and correctly produced no prices. The bounded readiness correction waits for current form controls plus the matching room-grid response, without another search or request. The reviewer inspected it and personally ran all five readiness regressions.
- The corrected live capture returned a genuine empty offer result for 29–30 September. The new narrow negative contract requires matching property, actual request, returned form, response date/party echo, boolean `isSoldOut=true` and an explicitly empty rooms array. It records unavailability only for that requested stay and allows the job to continue to later dates. Missing/contradictory structure, source errors and arbitrary flags remain unknown.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

```text
.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 372 tests in 21.620s — OK.

node --check compset/static/app.js
Passed.

git diff --check
Passed; only working-tree LF/CRLF notices.
```

The final suite includes 17 independently authored tests, 15 Booking/Expedia tests and 28 MakeMyTrip/Agoda tests. Earlier full runs of 361 and 366 tests were followed by the final run because the readiness and verified-negative implementations changed.

The independent tests personally exercise isolated temporary SQLite databases and prove:

- Exact duplicate ingestion is idempotent; changed parser interpretations and changed raw captures append history while preserving the first amount and original raw content.
- Cache isolation by hotel, source and complete frozen request context, including typed party/date/currency; stale and future-dated evidence are not reused.
- Cached raw is reparsed by the current parser with zero network calls, producing a new interpretation while retaining the original capture and interpretation.
- Zero-budget and paused jobs make no capture calls and preserve all 150 source/date cells as unknown.
- A failed source or malformed parser response does not abort a separate source; first visits are fairly distributed across sources.
- Approximate prices cannot become exact quotes; valid direct-OTA displayed prices remain indicative.
- Verified negatives require the exact typed observed context, cannot contain contradictory positive rates, cover one date only and do not stop a later date.

I independently reparsed both the initial Agoda projection and the owner's packaged capture using the frozen parser. Each yields **14 accepted indicative offers across five room types**, from 24 raw offers with alternate occupancy and product variants. Every accepted amount agrees with both numeric and displayed source fields at its recorded JSON path. The observations bind Hotel Aketa ID `110205`, 28–29 September 2026, one adult, one room, zero children and INR. All remain displayed prices, not precise final checkout quotes. Before-tax semantics, meals, cancellation, payment, membership and coupon conditions remain attached; fee inclusion remains unknown.

For each of those two captures, eight direct mutations—HTTP 429, challenge, wrong property ID, wrong property name, wrong returned guest count, contradictory sold-out flag, different requested party and missing returned checkout—produce no rates. An added earlier two-adult response does not erase the 14 verified one-adult offers. Original source bytes remain unchanged.

I separately reparsed `data/hotel-pipelines/readiness-proof/latest-capture.json`. It contains the successful owner-executed post-navigation read for **29–30 September, one adult, one room, zero children, INR**, with an explicit empty offer result. Eight mutations of its availability flag, required rooms array, property/party echo and HTTP status prevent a verified unavailable result. The source bytes remain unchanged. Read-only inspection of the production SQLite database confirms that the earlier `currency_not_verified` failure and later verified negative remain in history; the repair did not delete or rewrite the failed capture.

The saved Booking evidence parses as `blocked/challenge_detected`; Expedia as `blocked/access_or_rate_limit_429`. The preserved MakeMyTrip `200-OK` diagnostic parses as `unknown/source_contract_unavailable`, retains its original observation timestamp and makes no fresh-network claim. None emits a price or an unavailable date.

## Final saved report and UI proof

At `2026-09-28T06:02:52.887019+00:00`, the saved five-source report contains **150 source/date cells: 31 indicative, one verified unavailable stay, 118 unknown, zero exact supplier quote cells**. Its 51 price rows comprise 37 Google-origin rows and 14 Agoda-origin rows. The one unavailable cell belongs only to Agoda for the 29 September arrival; it says nothing about physical occupancy or bookings on other channels.

I read `/api/hotels/aketa` and `/exports/hotel-aketa-rates.csv` from the existing `127.0.0.1:8765` runtime. Both returned HTTP 200, `Cache-Control: no-store`, and bytes exactly equal to their saved artifacts.

I executed the actual `renderHotel` function in Node with a DOM stub, without a browser. The all-source table contains 170 rows: 51 price observations, one unavailable stay and 118 unknown cells. Source filters retain the correct counts: Google 37 price rows; Agoda 14 price rows, one unavailable stay and 28 unknown dates; Booking, Expedia and MakeMyTrip each retain 30 unknown dates. The header says partial and uses the pipeline timestamp; source status labels identify the last checked arrival. No visual browser inspection is claimed.

## Reviewed source identity

| File | SHA-256 |
| --- | --- |
| `compset/hotel_contracts.py` | `69f64fdbf0861ab1bf206a47b65897038b254ce3455ad3884c56b39fd8d3505b` |
| `compset/hotel_store.py` | `fd4e9c4fdb085ba4bd016fffe40f0bbcbae458917a2f62f745c2d77138bd612a` |
| `compset/hotel_jobs.py` | `1192e4b9cc626dd5d094ab4b3b2008400107b2fbe52efa49639b11331f97659f` |
| `compset/hotel_booking_expedia.py` | `457699675a6d6e3fb9942742cffa84ba9b545c1e148d6c0a1106fb73cec6e299` |
| `compset/hotel_mmt_agoda.py` | `51ae15936b32f21b719b1869bcbdbb08fdf159987120299851d31d203815d14d` |
| `compset/hotel_aketa.py` | `bc3b3201c522d5af86171334abd51c5e653ced6257d9b3febe0f9e71e56323b4` |
| `compset/__main__.py` | `99f5fc0fe7ed19c48d6c8763095137017baa4eba12c88f7a16b278fbdb8c6ac3` |
| `compset/static/app.js` | `7c42c9c2bd0c7544d644f42f0a9b4f2d4ad876edea412e183ad57abb34142230` |
| `compset/static/index.html` | `84c384d5f3b103a6c425244756afd1b3b03f526bda561b21847fd5554670f018` |
| `tests/test_hotel_portfolio_review.py` | `7b41e7f3fa18daafd561a8d38ae02ae316b2f83e5449c585b3ccc95127159c68` |
| `tests/test_hotel_booking_expedia.py` | `433fe59e814eb19097750d8607c3dac8af4967aed46c1da34bcbc716a14e84c5` |
| `tests/test_hotel_mmt_agoda.py` | `95430e0a05af1a10dac76a47677782b55e4d25ff6369dda9ba96ec1a11535a10` |

| Evidence | SHA-256 |
| --- | --- |
| `data/hotels/aketa/agoda-verified/agoda-20260928T054705192569Z.json` | `610d064130611421d9e45cf37f29f52252add36f4a20f6afdc27928ffb3a3c33` |
| `data/hotels/aketa/agoda-packaged-proof/agoda-20260928T054814068388Z.json` | `e1ab98e99ef795495f58a83122f4b382551ad6d7d94461725dbe8d5c535ae051` |
| `data/hotel-pipelines/readiness-proof/latest-capture.json` | `7cfbd11b0c1725c3b3f8911d9c41303b104b2689589a3b48a4a28c960cbb3448` |
| `data/hotel-pipelines/latest.json` | `94865c7d9583bd274f749999ea620278d5b43d9966e579a3f602b256a16c2476` |
| `data/hotels/aketa/latest.json` | `ad8ce4fb205a0ddcb923c19e103729bc9b4dc05d3272ddcb3135eff8a4a725d1` |
| `data/hotels/aketa/rates.csv` | `29e2ca8d88bbfd5477a1b02cea4c73c5f9424f01523864b6cb74d37ec20e1174` |

## Limits

This rollout is Aketa only. Booking identity/price access remains unverified behind its challenge; Expedia exact-stay access is blocked; MakeMyTrip has a preserved unusable-response diagnostic. Google observations are indicative and do not confirm room count. Agoda has one priced stay and one verified empty-offer stay, with the remaining 28 dates uncollected. No checkout, reservation, login, spending, identity rotation or access-control workaround occurred. Cache reuse is limited to six hours within the same frozen window. Future page or schema changes may produce explicit partial/unknown results and require new contract evidence.
