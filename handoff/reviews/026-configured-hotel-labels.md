# Independent review: configured hotel labels

Reviewer: `/root/workspace_data`, 28 September 2026. Backend implementer: `/root`.

Scope: `compset/hotel_memberships.py`, its tests, and only the new configured-label loader/count/status/revision integration in `compset/intelligence.py`. The broader intelligence projection was authored by this reviewer and is independently covered by root's separate review. The final section separately accepts the narrow frontend addition implemented by `/root/ota_review`.

Backend result: accepted after correcting unknown label counts. This was an offline saved-data review; no source requests, account actions or server restart occurred.

## Finding and correction

The first summary integration defaulted `configured_label_count` to zero when the sidecar did not exist, was invalid, or contained no observed group for a known subject. Those cases are unknown, not an observed empty comparison. Root replaced that default with `null` and a `configured_label_status` of `not_observed` or `read_error`. An explicitly observed empty group remains zero with `observed_name_only`. Independent regressions cover all three conditions and unknown/non-subject IDs.

The loader projects only validated names under an exact imported subject ID. It never creates competitor IDs or relationships by matching names, even when a label exactly equals an existing competitor profile title. It always reports zero verified competitor IDs and zero collected rates for this evidence type. Unknown or duplicate subject groups fail closed; error strings do not echo raw input. Source URLs use the existing Lighthouse allowlist and omit query/fragment data. Unknown nested fields, credentials and invented price/ID fields do not enter the projection.

The sidecar's file signature participates in the source revision. Independent edit/delete tests verify revisions change, new names appear, old returned values are not mutated and deleted observations are not retained. The original observation timestamp is preserved rather than replaced with projection time.

## Personally executed proof

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_hotel_memberships tests.test_hotel_memberships_review tests.test_intelligence -q
```

Result: **23 tests passed**, 2.928 seconds. Five reviewer tests add explicit unknown versus empty coverage, unknown/non-subject ID rejection, exact-name collision without a fabricated relationship, secret-safe field projection, timestamp preservation, edit/delete revision behavior and invalid source/timestamp/schema rejection.

The reviewer also directly loaded the actual saved sidecar through both public projection functions. Result: six exact subject groups and **42 name-only memberships**, with counts 2, 9, 6, 9, 6 and 10; **zero verified competitor IDs and zero collected rates**. Summary and hotel payload both reported revision `6a9062bb325a9a4aa450` for that read. This checks projection conservation, not independent verification of the authenticated account observations.

## Reviewed SHA-256

| File | SHA-256 |
| --- | --- |
| `compset/hotel_memberships.py` | `9e49c3f5f17fba2dc30adaa17217b673f5910c2323f3547de8264977d107b563` |
| `compset/intelligence.py` | `7640af5413012063b1aad780e5195be06f5efbb9285465a62b1e85d9fb07d4c3` |
| `tests/test_hotel_memberships.py` | `947f4b6a1038c949e823431d73aa95454f4d546b5d5ed889b311a09e4a71e9de` |
| `tests/test_hotel_memberships_review.py` | `5daa2e8611d3c141cbeff046e13d284c72d939485d31f8e862e760beefa108dd` |

## Narrow frontend addition

Implementer: `/root/ota_review`. Result: accepted at the hashes below after independent source inspection and executable tests. This extends, rather than replaces, the earlier dual-workspace review in `022-dual-workspace.md`. CSS was unchanged. No browser was opened, so visual/device behavior remains outside this acceptance.

The selected imported hotel resolves exactly one group by `subject_id`. Missing, invalid or duplicate groups remain unknown. Names render as plain table text rather than property IDs or interactive rate identities. The view marks OTA identities unverified, rates not collected and coordinates unknown; map mode does not invent locations. Observation time and source link remain attached to the group. CSV includes subject identity, the observed name, identity/rate status and provenance, with spreadsheet formula escaping. It contains no invented competitor-ID, price or currency columns.

The reviewer added three narrow Node tests for missing versus empty groups, CSV semantics and exact-subject rendering. A synthetic DOM test confirms that selecting a subject shows only its names, never another group's names or Aketa rates, performs only local GET requests and does not turn names into hotel links. Existing stale-response and collection-identity tests also remain green.

Personally executed:

```powershell
$env:COMPSET_DUAL_REAL_DATA='1'
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js
```

Result: **29 tests passed**, 2.531 seconds, including actual saved data and the six configured subject groups. No source collection, phone action or persistent runtime change occurred.

| File | SHA-256 |
| --- | --- |
| `compset/static/dual-workspace.js` | `e615efe82879cd427d5bd2b26b496683facfc6e6a6535bb7e7479143781c2e97` |
| `tests/test_dual_workspace.js` | `66dcc7e6b5f839db652d41e151037221c3e8b97a251788a5c53ca5c9c8b524cb` |
| `tests/test_dual_workspace_review.js` | `47a98e591d51c9e133b962bf7110169d27e341c339b33ed47ff319651ba1d3a1` |
| `docs/dual-workspace-contract.md` | `9d43e9b84104a9c7eadd3b05044890735789c15c7a392f18d6c1959c4cc7df66` |
