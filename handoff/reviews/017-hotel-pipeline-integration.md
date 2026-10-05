# Order 008 integration and source results

Owner: root. Standalone `C:\Users\astha\CompSetStudio`. User clarified Aketa only. Yellow, bookings, credentials, payment flows and recurring automations were not changed.

## Implemented scope

Explicit Aketa mappings for Google Hotels, Agoda, MakeMyTrip, Booking.com and Expedia; strict shared price/context contracts; source adapters; source/date planning; serial finite capture calls; fair first-canary allocation; six-hour frozen-context cache; raw reparse with parser dependency hashes; append-only SQLite evidence; atomic checkpoints and cooperative pause; JSON/CSV exports; source-filtered saved-price view. Existing server routes serve the attached data without a process restart or new write endpoint.

Google observations retain origin `google_hotels` and the supplier as a separate channel. Direct Agoda observations require matched property ID, actual request/response dates and party, visible INR/form state, per-offer one-adult/one-room occupancy and matching numeric/display amounts. They retain integer-display precision, before-tax basis and public member/coupon conditions. No checkout total is invented.

## Source evidence

- Google: original capture `data/hotels/aketa/google-form-canary-complete-2026-09-28.json`; 30 calendar values and seven partner display observations. Five abbreviated prices have no exact amount.
- Agoda: property ID110205. The original projected room grid contains 24 offers; fourteen matching one adult/one room across five room types are normalized, with ten two-adult alternatives retained only in raw data. Packaged first-date capture: `data/hotels/aketa/agoda-packaged-proof/agoda-20260928T054814068388Z.json`.
- MakeMyTrip: property ID202108231240265962, but actual dated response contained only `200-OK`. The adapter saved its historical diagnostic with zero repeated source requests: `data/hotels/aketa/mmt-diagnostic/makemytrip-20260928T055155245520Z.json`.
- Booking.com: primary-source robot-verification challenge. Saved diagnostic: `data/hotels/aketa/direct-ota-evidence/booking-latest-capture.json`. No verified direct quote contract.
- Expedia: property ID92850456 verified, then exact-date search returned HTTP429 followed by challenge validation HTTP403. Saved diagnostic: `data/hotels/aketa/direct-ota-evidence/expedia-latest-capture.json`. No further attempts or verified direct quote contract.

The generic job's first next-date Agoda capture reached the localized property URL but read empty DOM before results loaded. It returned unknown, not a fabricated quote. Its raw response and failed interpretation remain in the database: `data/hotel-pipelines/raw/b08c3eae4463e1b05376a6edef1378e107f3840ea02945fe6d32ae94e75a3423.json`.

After a bounded readiness correction, the packaged capture waited for both current rendered controls and the exact submitted room-grid response. `data/hotel-pipelines/readiness-proof/latest-capture.json`, observed at 2026-09-28T05:58:55.232472+00:00, returned HTTP200, verified Aketa/29-30 September/one adult/one room/zero children/INR, explicit boolean `isSoldOut=true` and `rooms=[]`. The current parser records a verified source-specific unavailable stay with no price. Earlier unknown interpretations and original raw bytes remain in history. The planner continues to later dates after a verified negative; missing fields and conflicting evidence still stop that source as unknown.

## Verification

Root personally executed registry initialization, offline import of all five sources, cached orchestration, source/date export checks and existing-loopback API reads. The original five-source snapshot held 150 unique source/date cells, 31 indicative cells, 119 unknown cells and zero exact supplier-quote cells. Raw and interpretation history remained separate; SQLite integrity was `ok`. Independent code, negative-context, history, API and JavaScript-render proof is in review016. No browser inspection of localhost was retried after the earlier browser-policy rejection.

The final offline republish (`hotel-run --dashboard`, zero capture calls) produced job `12312b00d4d1549a2f11caa56f408dea1c5ef38542f176ee7a53d088a2ceb68b`: 150 source/date cells, 31 indicative, one verified unavailable and 118 unknown, with 51 rate rows (37 Google and 14 Agoda). The unavailable cell is only Agoda arrival 29 September/departure 30 September; later dates remain unrequested. `node --check compset/static/app.js` and `git diff --check` passed. Final independent suite and approval are recorded in review016.

Reviewer `/root/ota_review` accepted the frozen implementation after personally running **372 tests in 21.620 seconds**, context mutations, API/export equality and actual JavaScript rendering with a Node DOM stub. Root then independently read the current API and both CSV exports, asserted 150 unique source/date pairs and 51 rates, checked the single unavailable date, verified SQLite integrity and confirmed that both the earlier unknown interpretation and corrected unavailable interpretation remain stored for the same raw capture. All final checks passed. Review016 records the source and evidence hashes.

The direct Booking.com/Expedia price parsers and MMT's usable pricing contract remain incomplete. Those adapters provide real capture/health diagnostics; they are not represented as functioning direct quote pipelines. The user can see both working sources and explicit gaps in the same report.
