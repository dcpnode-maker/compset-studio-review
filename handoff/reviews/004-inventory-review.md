# Order 004 independent inventory review

Reviewer: Codex sub-agent `/root/scrapling_research`. Implementation owner: root agent. Scope: new `compset/inventory.py` ingestion, identity, monetary context, and SQLite/JSON/CSV preservation. The reviewer did not implement this module and edited only `tests/test_inventory.py` and this review record. The reviewer previously implemented profile/normalization helpers; this is not an independent review of those helpers. UI/XSS and collector network behavior are reviewed separately.

Status: **accepted for the reviewed inventory component**, with no open findings. All implementation findings below have been fixed and reviewer-executed regressions pass. No production requests were made by the reviewer; persistence tests use temporary directories.

## Findings and regressions

1. Duplicate Airbnb listing IDs could produce two in-memory records but one SQLite row via `INSERT OR IGNORE`. Root fixed ingestion to reject missing/duplicate channel IDs. Reviewer executed the duplicate-identity regression successfully.
2. A verified quote label originally promoted bookability with absent provenance or nonpositive stay length. Root added source/time/guest/interval requirements. Reviewer executed regressions for absent evidence, zero/missing/Boolean guests, zero price, missing currency, malformed dates, and equal/reversed canonical dates successfully.
3. `date.fromisoformat` accepted basic/week ISO forms, but the interval check compared the original strings. `checkin='2030-10-17'` with `checkout='20301016'` or `'2030-W41-1'` promoted bookability despite checkout preceding checkin. The reviewer personally reproduced both failures. Root restricted accepted dates to canonical `YYYY-MM-DD`; the reviewer re-executed the mixed-ISO regression successfully.
4. A raw `after_discount.total` quote with missing/malformed stay context threw `KeyError`, `ValueError`, or `TypeError`, aborting inventory import. Root now skips normalization of prices with invalid dates while preserving the observation. Reviewer re-executed all three failing cases successfully.
5. A detail UUID different from the catalogue UUID prevented ACTIVE promotion but still permitted its calendar and website total to attach to the catalogue row. Root now guards derived fields against an explicit catalogue identity mismatch, retaining the raw observation and a warning. Reviewer re-executed the failing wrong-property regression successfully.
6. Matching fresh details initially updated only description, leaving stale catalogue capacity/bedroom/bathroom/amenities values in the canonical row and profile. Root now maps fresh fields and rebuilds the canonical profile. Reviewer reproduced the original capacity 4 versus fresh capacity 6 failure, then executed the corrected test successfully.
7. The first fresh-field mapping cleared known description/amenities when partial details lacked them and relabeled old capacity with a missing fresh-field source. Root now imports and updates provenance only for usable observed fields. The reviewer reproduced the failure, then passed the regression for preservation of both known values and their evidence. The reviewer additionally passed checks for all mapped field sources and the bathroom-count fallback source path.
8. Root identified 8,604 real calendar placeholders with `inventory_uuid: null`, no property/room ID, matching property UUID, and zero count/prices. The reviewer independently counted all 8,604 and inspected the actual first record (property `242522`, `2026-09-01`, UUID `de8af4cd-63c7-4a2e-bb2b-3bca812623c0`). These now remain `unknown` with reason `inventory_record_missing`; zero prices remain null. A reviewer-written regression proves matching UUID placeholders are retained and explicit mismatched IDs/UUIDs are rejected.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

1. `.venv\Scripts\python.exe -m unittest tests.test_inventory -v`: 13 tests passed before the mixed-ISO regression was added. Tests cover exact decimal strings, zero/unknown prices, search-display versus verified dated quotes, full/deep source retention, three currencies, absent canonical values, explicit cross references, same-name/different-ID hosts, duplicate identities, optional supplement import, repeated snapshot ingestion, old/new observations, and JSON/SQLite/CSV round trips.
2. `.venv\Scripts\python.exe -m unittest tests.test_inventory.InventoryTests.test_quote_label_cannot_override_missing_or_invalid_stay_context -v`: two failing mixed-ISO subcases, proving finding 3.
3. An offline Python proof loaded `data/bnbme-catalog-source.json`, normalized every record, persisted twice into a temporary SQLite database, compared every raw attribute with the JSON, SQLite `record_json`, and CSV `attributes` output, and ran `PRAGMA integrity_check`. All assertions passed:
   - Source file SHA256: `6050a03153d4a7b256ec92abea2b0b886f46e9d5cb3ee11dde4dee4510db8297`.
   - Catalogue-only snapshot: `0464b30cde57006c163bb017`.
   - 113 unique properties; every nested public source field retained in all three exports.
   - 67 Dubai/AED, 35 Riyadh/SAR, 11 London/GBP.
   - One SQLite snapshot and 113 property rows after repeat persistence; integrity check `ok`.
   - 98 properties with advertised display prices (67 AED, 31 SAR observations); zero verified bookable properties. London prices remained missing, not zero/free or converted.
   - Corporate active inventory completeness remained false.

4. Detail/calendar regressions additionally verify explicit ACTIVE status separate from bookability, exact `after_discount.total` preservation, retained charge breakdown, unknown/Boolean/negative/fractional inventory counts, wrong calendar ID/UUID/date rejection, and calendar SQLite/CSV round trips. Those cases passed. The missing-context and catalogue-UUID attachment cases failed as findings 4 and 5; the separate canonical mapping regression failed as finding 6.

5. Final `.venv\Scripts\python.exe -m unittest discover -s tests -q`: **130 tests passed in 6.612 seconds**, personally executed after the above fixes. The inventory module has 23 reviewer-written tests. Execution of the broader suite does not assert independent source review of previously implemented helpers.
6. Final offline enriched-source proof loaded the full catalogue and all 113 cached detail observations, called `build_inventory` and `persist_inventory` into a temporary directory, and personally asserted:
   - All original catalogue attributes and full original detail observations match the JSON and SQLite round trips exactly.
   - All public catalogue and detail attribute objects match the property CSV exactly. Raw detail envelopes remain in JSON/SQLite; calendar records have a separate CSV.
   - All 41,245 normalized calendar records exist in SQLite and calendar CSV; exactly 8,604 are unknown placeholders, while 32,641 are explicit public inventory count observations.
   - 113 ACTIVE properties, 62 properties with website stay totals, zero verified bookable properties, and unchanged separate AED/SAR/GBP currencies.
   - `PRAGMA integrity_check` returns `ok`.
   - Detail source SHA256: `4670797f0e4354f53638ef4a3ead4ec88feb41f7ae238652c29a54e8dedc88c0`.
   - Reviewed enriched snapshot: `d65473050f65ebee670e9ae6` (catalogue/details only, intentionally excludes separate host/channel supplements).

Reviewed inventory implementation SHA256: `96a45b1a0a1313156f62e7eafad1536cf43d819ba41ebcd8d5d4c03e082eedd2`. Reviewer test file SHA256: `cd90d325de1eb351cc4494a9437265e70450196860e9f7824a432b884515e41b`.

## Scope limits

The reviewed component's acceptance checks are complete. Website inventory counts are not booking-status evidence; website stay totals do not promote verified bookability. Complete capture of these 113 catalogue rows does not establish complete corporate inventory. Public host/channel identities are retained separately and require explicit cross-reference evidence to link to direct properties. Network scheduling, UI/XSS, and API boundary source review are outside this component review.
