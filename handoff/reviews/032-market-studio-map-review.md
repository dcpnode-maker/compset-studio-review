# Order 022 independent map review

Reviewer: Codex visual implementation agent. I edited `dual-workspace.css` and `docs/market-studio-design.md`; I did not implement or edit the map JavaScript or its tests. Review performed on 28 September 2026 against the shared working tree before commit.

## Scope and findings

I inspected geographic circle and polygon validation, pointer capture/cancellation, the candidate/result update path, CSV export, source identity, local selection storage, and missing-map behavior in `compset/static/dual-workspace.js`.

Three local-set issues found in the initial implementation were returned to the map implementer and corrected before this receipt: malformed polygon/all storage could supply a missing radius and crash `updateMapView`; local selections were keyed only by subject rather than saved revision; Save during an active draft cancelled the preview but described an ambiguous save. The final code validates radius for every loaded shape, keys the set by saved revision, and states that the committed area was saved.

Two further issues found in the first frozen handoff were returned and corrected: Add coordinate vertex called an undefined `arm` function when no map was initialized, and the candidate table exposed only the first 25 rows. The final code disables and guards coordinate entry without the map/polygon layer and adds candidate table pagination, including manual inclusion and inspection beyond row 25. A >25 candidate fixture verifies that behavior.

Review of the corrected code found no further map JavaScript blocker. Circle and polygon edits remain local view state; they do not mutate saved decisions or collection scope. Unknown locations remain outside geometric counts, and exports use the committed area and local inclusions. A missing map still leaves candidate evidence available.

## Reviewer-executed proof

From `C:\Users\astha\CompSetStudio`:

```text
node --test tests/test_map_area.js tests/test_map_area_review.js tests/test_dual_workspace.js tests/test_dual_workspace_review.js
tests 73; pass 73; fail 0; skipped 0
```

The tests cover mouse/touch/pen draw, polygon preview/undo/apply/edit/clear, boundary and crossing geometry, cancellation and stale callbacks, source/revision guards, candidate inspection, CSV, local sets, >25 candidate paging, and no-request map edits. I also ran `git diff --check` over the JavaScript, CSS and focused test file; it returned no whitespace error. The environment had no available Chrome or in-app browser provider for visual acceptance. Rendering and live tile availability remain separate from this executable review.

## Adjacent hotel table review

The same reviewer inspected root's hotel calendar, one-row-per-offer table, shared Filter/Columns editor, and source/offer inspector without editing their JavaScript. The first pass found that a filter rerender could lose focus, the per-row action implied one offer while opening all offers, and Sort lacked a visible label. Root corrected the focus restoration, changed the action to “All offers”, and labelled Sort. I reran `node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js` after those corrections: 39/39 passed. This is executable DOM proof, not a browser rendering claim.
