# Order 007 independent saved-price and Hotel Aketa review

Reviewer: Codex sub-agent `/root/price_review`. Owners: `/root/dashboard_prices` (saved-price routes/UI), `/root/hotel_aketa` (hotel capture/parser/export), root (one-night report metadata/integration). This reviewer did not implement the changes and edited only this review. No external requests, browser actions, live data edits or persistent runtime changes were performed. HTTP verification was restricted to the existing local dashboard and isolated unit-test servers.

Status: **accepted for saved-price display/routes, hotel parsing/export and the observed dataset, at the hashes below**. Two independently reproduced hotel normalization findings were repaired by the implementation owner and personally retested. No open finding remains in that scope. The new packaged `capture_google()` function was inspected, and the owner's successful isolated live capture was independently reparsed as recorded below. This reviewer made no live browser call. The CLI wrapper itself was not exercised live, and no future refresh success is guaranteed.

## Findings resolved

1. **An unknown supplier inherited the previous supplier.** In saved Google snapshots `action 3`, `action 7` and `action 8`, replacing the exact `Agoda` heading with `UnknownRooms.com` attributed its INR 6,060/6,066 offer to Booking.com. The owner added an unknown-provider boundary guard. I reran the same three mutations after the freeze; no offer from the unknown supplier was emitted under another supplier. The owner also added a regression.
2. **Negative breakfast text was normalized as included breakfast.** Replacing `Free breakfast` with `Breakfast not included` in the real `action 7` snapshot produced `meals=breakfast` for three offers. The owner now recognizes positive inclusion labels and rejects negative labels. My repeated mutation retained all three raw negative descriptions with `meals=null`. The new regression also passed.

The owner additionally rejects calendar dates with conflicting observations, requires ordered source-bound adult/child proof, verifies the INR control and requires timezone-aware observation times. The corresponding negative tests were personally executed in the final suite.

After the first review freeze, root's attempted packaged live run failed before network access because Windows lacked IANA timezone data for `Asia/Kolkata`. The owner replaced the current/future India date calculation with the standard-library UTC+05:30 timezone. I inspected that correction, personally executed the default `requested_context()` successfully and reran the full suite, including both sides of the 18:30 UTC India date boundary and the default report path with IANA lookup unavailable. This runtime finding was reported by root; I do not claim to have personally executed the pre-repair failing live command.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

```text
node --check compset/static/app.js
Passed.

.venv\Scripts\python.exe -m unittest tests.test_saved_price_server tests.test_server -v
Ran 7 tests in 3.638s — OK.

.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 310 tests in 31.113s — OK, after the initial hotel code/data/test freeze.

.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 312 tests in 20.501s — OK, after the timezone portability correction.
```

The server tests cover missing/partial/non-object JSON, exact saved-byte preservation, unknown values, no-store/nosniff headers, host/origin restrictions, fixed-path traversal rejection and refusal to turn the saved-read endpoints into collection commands. I also personally fetched `/api/one-night`, `/api/hotels/aketa`, `/exports/one-night-prices.csv` and `/exports/hotel-aketa-rates.csv` from the owner's existing `127.0.0.1:8765` server. All returned HTTP 200, no-store, and byte-identical saved artifacts. This is API proof, not a browser-appearance claim.

I independently executed the actual `dateInput`, `localDate` and `expandOneNightCells` JavaScript functions in Node against the saved one-night report. The report contains 68 listing IDs. The resulting grid contains **2,040 date cells**, preserves every saved record unchanged and explicitly represents **455 uncollected cells** with no invented quotes. A two-listing synthetic report with no records still represents all 60 requested cells as uncollected. The source report was unchanged. Source inspection confirms escaped text-node rendering, separate exact/unknown/restricted states, contextual totals, separate alternate rate plans, and hotel indicative/abbreviated labels with unconfirmed room count.

I reparsed `data/hotels/aketa/google-form-canary-complete-2026-09-28.json` directly with the frozen hotel parser and compared the resulting report, including the source artifact path, with `latest.json`: **exact equality**. Independent assertions established:

- All 30 consecutive check-in dates, 28 September through 27 October 2026, with the next day as checkout; 30 calendar rows plus seven displayed partner offers for 28–29 September.
- Exact Hotel Aketa Google entity identity, one adult, zero children, INR and one-night duration. Observed room count remains null; requested room count is one and `room_count_verified=false`.
- All 30 calendar display labels agree with the raw line pairs identified by their saved source paths. Five abbreviated K labels have `amount=null`, retain their original display label and carry a separate approximate amount.
- `quoted_dates=0`, `unavailable_dates=0`, and every row has `direct_supplier_quote=false`. Taxes and fees remain unknown. The 30 dates are covered by indicative Google displays, not verified supplier checkout quotes.
- Changing the actual source hotel URL, setting two travelers, removing the adult/child decrement proof, returning HTTP 429 or setting a challenge stop reason each yields zero rates and **30 unknown dates**, never unavailable dates. These were direct mutations of copies of the saved source, not run-context-only changes.
- Input objects and original saved source bytes remain unchanged by parsing and all mutation proofs.

The existing price-core review 013 remains applicable to the extractor. The one-night orchestrator change inspected here adds `listing_ids` metadata so the UI can represent all requested cells even when no result was saved for a listing. The final full suite reruns the earlier price, transport, calendar, cache, versioning and SQLite history proofs.

After the timezone correction, root executed the actual packaged `capture_google()` and `export_capture()` functions with an isolated output directory. I personally loaded and reparsed `data/hotels/aketa/verification-20260928T051555Z/google-calendar-20260928T051618335748Z.json`, without making another request. Assertions verified HTTP 200, no stop reason, one navigation, zero direct replays, five snapshots and exactly four expected control clicks: two-traveler selector, Remove adult, Done, Check-in. Its exported report exactly matches my reparse: 30 indicative calendar rows, five abbreviated K labels with null exact amounts and five partner displays for the selected 2–3 October date. That selected date remains separate from the production dataset's 28–29 September offers. All rows retain unconfirmed room count and unknown tax/fee inclusion, with zero direct supplier quotes. The production `latest.json` hash remained unchanged. This establishes successful owner-executed packaged collection with independently checked saved evidence, not reviewer-executed network or a live CLI-wrapper proof.

## Reviewed identity

Initial hash capture: `2026-09-28T05:13:52.241632+00:00`; hotel code/test hashes updated at `2026-09-28T05:16:31.226225+00:00` after the portability proof. Saved hotel data was unchanged and again matched an independent reparse. Working-tree hashes identify this review snapshot; no claim is made that the earlier Git HEAD alone contains the work.

| File | SHA-256 |
| --- | --- |
| `compset/one_night.py` | `e01e36e2d45b847be1ee876f7a320456522e73b5330276de8c6f7919566ca47e` |
| `compset/hotel_aketa.py` | `bc3b3201c522d5af86171334abd51c5e653ced6257d9b3febe0f9e71e56323b4` |
| `compset/server.py` | `713d10101c6eb46b523a988612557bda5daa8c08ca9006f11e373c1c8fdd4d04` |
| `compset/static/app.js` | `62946e8f7a10db7952701e491e03ca9a463d5a2869b3574c3426881ee596c0c5` |
| `compset/static/index.html` | `303b7f7bb8544dba7b03c865427477486924572035504e288ddc0b5226c5b306` |
| `compset/static/style.css` | `8cc93be9376da9b6fd1d99e5a28935637378294c4effacdd749b6ad466739024` |
| `tests/test_hotel_aketa.py` | `00511023e495cf27648b1fb89b49438f248cf4be47fb37825d7bba19a3ee0062` |
| `tests/test_saved_price_server.py` | `602bb0e49574ae271d4263d5c9fdfb75b5a888844e7649e21437d1bab0ed45ed` |
| `data/hotels/aketa/google-form-canary-complete-2026-09-28.json` | `b88dedb33b2fb8f3c0009b2f6b39fdfb04d2c27c9090c52bfb1e715ec7e5feb6` |
| `data/hotels/aketa/latest.json` | `363b62e4c25ed632d12fd21db2e473307b7df072c6703ff34bbdab048d14e4e2` |
| `data/hotels/aketa/rates.csv` | `ea9fa2747b1a6f4e1b3b749ff85c9ed9ab54ae96dc94b95fd19f6eb804fe8bb1` |
| `data/hotels/aketa/calendar.csv` | `b908d068f7a19e6ea4eb3aa26c72f6fa276e84c539cf41dabc00157828fc10f3` |
| `data/hotels/aketa/verification-20260928T051555Z/google-calendar-20260928T051618335748Z.json` | `a84ecf56c612833729404717f76db709203dd68333f0faf0886ee9b31f5b71d9` |
| `data/hotels/aketa/verification-20260928T051555Z/latest.json` | `9d6857a67bc71843895410c30a9ff335c124a4de4642bb256e0e5cdaf385d661` |

## Limits

Independent UI work was code inspection, JavaScript execution and local API checks. The dashboard owner's earlier browser smoke is separate evidence; it was not repeated by this reviewer after the browser tool restriction. No OTA destination, booking flow, payment, login or final supplier quote was accessed. The hotel dataset is an observed Google calendar and one night's partner display options. Neither this review nor its passing tests establishes future source stability, market completeness or full exact Airbnb pricing.
