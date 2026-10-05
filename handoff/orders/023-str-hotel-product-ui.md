# Order 023 — STR and hotel product UI completion

Status: in progress, 28 September 2026.

Founder clarified that the entire CompSet Studio UI needs work. STR should let a user draw a circle or other shape and immediately inspect the observed properties inside it. The STR experience should use the interaction pattern of PriceLabs custom compsets; the hotel experience should make saved competitor rate evidence as usable as Lighthouse's calendar/table pattern. These are workflow references, not claims of data, pricing recommendations, live parity, or vendor integration.

## Scope

- `compset/static/dual-workspace.js`, `compset/static/dual-workspace.css`, `compset/static/index.html` only if required for the revised UI.
- Focused frontend tests in `tests/test_map_area.js`, `tests/test_dual_workspace.js`, and new focused tests if necessary.
- `docs/dual-workspace-contract.md`, `docs/market-studio-design.md`, `docs/market-studio-research.md`, this order, and a scoped review receipt in `handoff/reviews/`.
- Read-only source and saved-data inspection; existing local server and saved intelligence endpoints for acceptance.

## Ownership and gates

- STR map agent exclusively edits `dual-workspace.js` and `tests/test_map_area.js` until handoff.
- UI design agent exclusively edits `dual-workspace.css` and `docs/market-studio-design.md` until handoff.
- Hotel gap agent reviews source/data read-only. Root owns order, final JS integration after map handoff, tests, review and commit.
- Preserve source identity, saved decisions, unknown/unavailable distinctions, revision guards, collection ownership and CSV provenance. A drawing action changes only the local view. No new source collection, paid service, schema, or fabricated market metric is within this order.
- Run focused and full frontend tests, inspect saved-data behavior, and verify live served assets. Record whether browser visual/physical touch proof was actually available. Independent review for any high-risk change; this order targets reversible frontend UI only.

## Acceptance

1. A user can choose circle or polygon, draw/edit it, see which *observed located* STR candidates fall inside, inspect and locally include/exclude them, and save/reload a named local set. The map, result table, count and CSV agree. An unlocated candidate is clearly excluded from geometry without being described as rejected.
2. STR map control instructions, draft/committed state and no-results state are understandable without knowing implementation terms; useful filters and full candidate paging remain in view.
3. Hotel dates show source offer counts and comparable saved conditions; the table/calendar/inspector offer a clear path from a rate overview to exact room, meal, cancellation, payment, party, stay, tax and observation facts when recorded.
4. Desktop and mobile hierarchy, affordance and readability improve using Yellow's compact ribbon/table language. No browser appearance claim is made without rendered browser proof.
