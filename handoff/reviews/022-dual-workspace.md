# Independent review: dual STR and hotel workspace

Reviewer: `/root/workspace_data`, 28 September 2026. Implementer: `/root/ota_review`.

Scope: `compset/static/dual-workspace.js`, its CSS, frontend contract and tests. This review does not independently accept the reviewer-authored intelligence projection or portfolio comparison builder. Root shell and collection-controller integration are reviewed separately in `021-root-workspace-integration.md`.

Result: accepted for local code integration after two confirmed data-display defects were fixed. No browser was opened, no persistent server was restarted and no accommodation-source collection was performed. Visual fidelity, real-device accessibility and live browser interaction remain unverified; this review uses code inspection and executable Node DOM fixtures, including the actual saved-data projection.

## Findings and corrections

1. **Hotel rates inherited the STR mobile day.** `hotelView()` forwarded the STR `day` option to `calendarView()`, which filtered cells to that one date while the hotel grid retained its full date header. Other observed hotel dates consequently appeared missing, and export omitted them. The independent regression failed before the correction. The implementer now explicitly clears `day` in the hotel projection. The regression verifies both observed dates survive and CSV contains both rows.

2. **An old lazy candidate request could overwrite a refreshed view.** A candidate-detail request started at source revision v1 could resolve after Reload saved loaded v2, and its old audit would still paint because subject/candidate IDs matched. The independent DOM regression reproduced this with a stale-detail canary. Refresh now closes and invalidates pending details, and lazy detail also compares captured, current and returned source revisions. The regression confirms the old response cannot paint after refresh.

Both corrections are narrow and were personally re-executed by this reviewer against the corrected implementation. The original tests alone passed before these extra regressions, so these findings are additional proof rather than a restatement of implementer results.

## Personally executed proof

```powershell
$env:COMPSET_DUAL_REAL_DATA='1'
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js
```

Result: **22 passed, 0 failed**, 3.597 seconds. This includes actual saved projections for both modes, full-population filter query construction before pagination, source/currency/context separation, source-revision rejection, lazy comparison/map audit lookup, unknown versus unavailable display, offer-condition filters, spreadsheet-safe export, imported-hotel isolation and explicit collection-controller delegation.

Code inspection also verified that map/radius interaction remains a saved-data operation, direct-site and Airbnb namespaces remain separate, direct offers inherit the saved source context in the inspector, and selecting a hotel with no configured collection mapping disables fresh collection rather than borrowing Aketa rates. Closing/destroying the view invalidates pending work. CSS includes responsive layout rules and touch-target sizing, but these are not substituted for browser/device proof.

## Reviewed SHA-256

| File | SHA-256 |
| --- | --- |
| `compset/static/dual-workspace.js` | `eaa5e573c7c8e5e425677d7802c17d44715fe5e1562400e932564659ab761d96` |
| `compset/static/dual-workspace.css` | `ad9a1f33ac0ecc20a5c28299160e180e325715e0634647cb259cd92cfdbecab8` |
| `tests/test_dual_workspace.js` | `b452ba26e005591a9fc797628fba9f0862dcadbff0e5ea69a12f369f14aef542` |
| `tests/test_dual_workspace_review.js` | `f6740ff99c068833b9ef9fdd811bd0e75bbfb03fabded84d06ec89bdca3c9984` |
| `docs/dual-workspace-contract.md` | `ba66dbd01a817c175243aa1c63e522d9744aff5f56414f9916207425a0b1c02a` |

Later edits require review of the changed surface; these hashes identify the accepted version.
