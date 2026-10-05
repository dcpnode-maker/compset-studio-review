# Order 007 integration and live delivery

Integration owner: root. Date: 28 September 2026. Standalone repository: `C:\Users\astha\CompSetStudio`; Yellow was not edited. Independent implementation review is recorded separately in reviews 012, 013 and 014.

## Airbnb evidence

- The selected comparison set contains 67 competitors plus the subject. The saved one-night report and CSV represent all 2,040 unique listing/date cells for 28 September through 27 October.
- Two date cells have exact contextual one-night totals. The subject's 28 September total is AED650.40; 29 September is AED610.36 for the selected non-refundable option with an AED650.40 refundable alternative. Unknown tax/fee inclusions remain unknown.
- Calendar preflight skips 1,582 stays: 790 overnight-unavailable, 727 minimum-stay failures, 60 arrival restrictions and five departure restrictions. These categories do not establish booked occupancy.
- The remaining 456 price cells are unknown. The resumed browser bootstrap timed out before source data arrived. One bounded direct connection diagnostic also timed out; no proxy/identity change or repeated retry loop followed.
- A separate saved canary proves AED377.04 before taxes for competitor1628828740875062740 on 30 September. It is outside the latest job's two-quote count and is not silently counted as completed batch coverage.
- Root personally read the final report, verified CSV row count equals unique listing/date count, verified the original subject still owns `latest.json`, and ran SQLite `PRAGMA integrity_check`: `ok`.

## Hotel Aketa evidence

- Google Hotels supplies 30 indicative one-night calendar minimums, 28 September through 27 October, INR, with observed one-adult/zero-child traveler controls. Five prices use abbreviated K displays and have no exact numeric amount.
- Separate partner displays for 28–29 September retain supplier/room/conditions as observed. The artifact contains seven partner observations; this is not a claim of seven unique suppliers or rate plans.
- Requested room count is one; observed room count is null. Taxes and fees are unverified. No row is a verified supplier checkout quote. No missing price or source failure is labeled sold out.
- MMT's dated canary returned an unusable HTTP200 `200-OK` body. The ordinary Google calendar supplied the useful follow-on data without a 30-request per-date batch.
- Source captures, `latest.json`, `rates.csv` and `calendar.csv` remain in ignored local `data/hotels/aketa/`. Offline reparse preserves original observation time.
- Root's packaged-function check initially exposed a Windows missing-IANA-timezone dependency before any request. The owner repaired local-date calculation and added boundary/portability tests. The final isolated `capture_google()` plus `export_capture()` run returned HTTP200, all four expected form actions, 30 calendar rows, five abbreviated prices and no stop reason. Its separate five partner displays belong to 2–3 October. Evidence: `data/hotels/aketa/verification-20260928T051555Z/`; the dashboard's original dataset was not overwritten.

## Dashboard and exports

- The previous process and original port8765 listener were absent before startup. Root started a new hidden loopback-only server without killing/replacing a process or choosing another port. Launcher19544 owns child9464, which listens on127.0.0.1:8765.
- Root personally verified HTTP200 for status, Airbnb saved-price JSON, Hotel Aketa JSON and both price CSV exports. The hotel API reports 30 indicative dates, zero verified supplier quote dates, and null observed room count.
- Dashboard implementation agent completed a local desktop/mobile smoke check before root's attempted browser inspection: full2,040-cell grid, status filters, portfolio navigation and no page errors. Independent review additionally executes the grid expansion without a browser.
- Root's later CUA request to inspect the local page was rejected by browser URL security policy. No alternate browser or raw automation workaround followed. Runtime delivery is supported by direct local API checks; root does not claim a subsequent visual inspection.

The software/export delivery is separate from completion of live Airbnb prices. Collection remains partial and manually resumable; no recurring scheduler or background price collector is enabled.

Final independent full-suite proof: **312 tests passed**, recorded in review014. JavaScript syntax and fixed-route access tests passed. Root's final `git diff --check` passed. No additional tests were repeated after documentation-only changes.
