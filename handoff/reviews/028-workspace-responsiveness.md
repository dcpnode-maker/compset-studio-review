# Independent review: Order016 workspace responsiveness

Reviewer: `/root/workspace_data`. Implementer: `/root/workspace_ui`. Reviewed 28 September 2026.

Scope: Order016 changes to `compset/static/dual-workspace.js` and `.css`, `tests/test_dual_workspace.js`, `docs/dual-workspace-contract.md` and `docs/dual-workspace-performance.md`. The reviewer added only `tests/test_workspace_responsiveness_review.js` and this report. Earlier reviewer-authored data projections are not independently reviewed here.

**Result: accepted for local code integration after two reload/context findings were fixed.** The reviewer personally executed all commands below against the accepted files. No browser, local server, runtime activation, source collection or ADB/device action was used. This acceptance does not establish measured browser latency, visual quality, screen-reader behavior or a speed advantage over any vendor.

## Findings fixed before acceptance

1. **Navigation during a pending summary reload could populate an obsolete cache.** Start Reload saved with revision R1 visible, hold the summary request, navigate to Hotels and allow its R1 response to be cached, then complete the summary with R2. The new view reused the intervening R1 cache and rejected itself as a source-revision mismatch instead of obtaining an R2 view. The reviewer regression failed with one hotel read instead of two. Summary acceptance now establishes another read boundary: it advances the view sequence, closes/cancels old details, aborts intervening requests and clears their cache before loading the accepted summary's view. The regression now passes without a source-change error.

2. **A removed subject's map center survived selection of a different fallback subject.** Drag subject A's map, then reload a summary that no longer contains A and falls back to subject B. The old custom center remained and positioned B's new map around A's location. The reviewer regression failed with the old Dubai coordinates instead of the replacement London's observed coordinates. The implementer now resets center, radius and candidate page and releases the map when reload changes the selected subject. The test verifies B starts at its own location and an old map callback cannot change it afterward.

Both tests failed against the submitted implementation and were personally rerun after correction. The reviewer did not implement either source fix.

## Personally executed proof

Environment: Windows, Node `v24.19.0`, repository Python environment for the optional saved-data fixture.

```powershell
$env:COMPSET_DUAL_REAL_DATA='1'
$env:COMPSET_DUAL_BENCH='1'
$env:COMPSET_DUAL_BASELINE_REF=$null
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js tests/test_workspace_responsiveness_review.js
node --check compset/static/dual-workspace.js
```

Result: **44 tests passed, 0 failed**, test-runner duration 2.964 seconds. Syntax check passed. A scoped `git diff --check` passed; only the repository's LF-to-CRLF conversion notices were printed.

The four new independent tests cover the two findings above, late-response isolation when `AbortController` is unavailable, and actual retained marker-set reconciliation when shrinking/enlarging a map radius. The latter uses a fixture with a real set of attached fake layers: out-of-range markers are removed, returning markers are added once, repeat edits do not duplicate them, the map instance is retained and no intelligence requests occur.

The full run additionally exercises cancellation during JSON decoding, coalesced reads, replacement generations, stale promise cleanup, failed-read retry without caching, source-revision/context guards, cached navigation, responsive breakpoint changes, selected-day/source hotel rendering and CSV scope, source price basis/conditions, unknown availability, modal focus containment and release, connected focus fallback, fixed collection identity, configured hotel-name isolation and actual saved projections in both modes.

## Independently reproduced offline measurements

The reviewer executed the benchmark against the exact older Git source without checkout or mutation:

```powershell
$env:COMPSET_DUAL_BENCH='1'
$env:COMPSET_DUAL_BASELINE_REF='b0a34cfd02a855d37949a89b585b6dd0a898b49d'
node --test --test-name-pattern='repeatable offline' tests/test_dual_workspace.js
```

The updated benchmark ran in the full command above. Both matched the performance document's counters for 25 properties × 14 dates, a simulated 390px viewport and 60 saved candidate points.

| Fixture measurement | Older commit | Accepted Order016 |
| --- | ---: | ---: |
| Initial elements constructed | 3,884 | 561 |
| Retained descendant nodes | 1,811 | 266 |
| Hidden desktop rate buttons constructed on mobile | 350 | 0 |
| Elements constructed for one mobile day change | 1,778 | 140 |
| Elements constructed for one map radius edit | 371 | 25 |
| Map instances across opening and radius edit | 2 | 1 |
| Tile layers across those operations | 2 | 1 |
| Map removals during radius edit | 1 | 0 |
| Zoom after edit, initially 16 | 13 | 16 |
| Intelligence reads during radius edit | 0 | 0 |

These are deterministic JavaScript/DOM fixture counters. They support a claim that the implementation constructs fewer elements and avoids rebuilding the map. They do not measure layout, paint, tile transfer, actual network latency, source collection time or commercial-product performance. The document appropriately separates those limits.

## Inspected behavior and remaining limits

- Only the active desktop/mobile calendar representation is constructed. The mobile hotel branch presents the selected day as source rows; `hotelDay` is separate from the STR selection. Each row retains its own currency, amount basis and state. Export scope follows the visible mobile day or explicit all-date table; no cross-source minimum is introduced.
- The 24-entry cache is populated after view identity/revision/context validation. Pending GET ownership, cancellation and generation guards prevent superseded results and cleanup from replacing newer work. Failed reads are not cached. The new summary-acceptance boundary also handles navigation during reload.
- Map identity includes mode, subject and source revision. Radius/center changes update existing layers; point popups are lazy. A same-subject decision filter can retain the full observed map point set while refreshing the paginated audit. Subject/mode changes and destruction release the old map; stale callbacks are identity-guarded.
- The inspector is modal at the specified tablet/mobile breakpoint, sets background regions inert, contains keyboard focus among usable controls, handles Escape and restores a connected target after close/reload. Desktop remains nonmodal. These code and fixture checks are not a substitute for a permitted browser and assistive-technology pass.
- Collection behavior remains delegated to the existing persistent controller. The reviewed navigation, map, layout, reload and filter operations do not create source-collection POSTs. No collector, schema, proxy, server or device configuration changed in this order.

Actual permitted desktop/mobile visual review, first-usable-view timing, cold/warm browser timings, real Leaflet tile behavior and screen-reader checks remain outstanding. No Koel Jain attribution was invented; the exact intended reference remains a separate input.

## Accepted SHA-256

| File | SHA-256 |
| --- | --- |
| `compset/static/dual-workspace.js` | `0b7f13cd5ad2c8c09e3a89b1a9a65de82b7253ce54783ea69506d234c703a2a0` |
| `compset/static/dual-workspace.css` | `8a001d9c864ea8ebc167127a761c8de0f2b50032a2bd8e0f81230a4ee0fff17f` |
| `tests/test_dual_workspace.js` | `1635065137172fb45867cf04ef761927ea3979f22edb44408d94bb2ab231b30d` |
| `tests/test_workspace_responsiveness_review.js` | `200524eab0ce6b961287ea9855edadf6a85c8bd60038c47a1d4724f9bfb89914` |
| `docs/dual-workspace-contract.md` | `0c8921afd103bdbde336ca739ef5547f6baed5efa98a98e5b5db7c824f934eeb` |
| `docs/dual-workspace-performance.md` | `0c17a8989a0b407d5e5277f25928a5e354ea8b82b0744ea8d62961c356f8685c` |

Later source edits require review of their delta; these hashes identify the personally checked implementation and documentation.

The final documentation-only amendment was inspected after the executable freeze. It describes summary-acceptance invalidation, fallback-subject reset and the four new reviewer tests, with the complete 44-test command. The documentation hashes above include that amendment; implementation hashes and measurements were unchanged.
