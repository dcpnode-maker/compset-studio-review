# Order 022 - Research-led Compset Studio redesign

Status: implemented and source/HTTP verified, 28 September 2026. Browser visual acceptance remains open because the available Chrome and in-app browser providers returned Browser not available.

Founder requests a better map drawing workflow, research of each PriceLabs and Lighthouse module, and a functional redesign using Yellow UI elements. Follow-up explicitly authorizes parallel lower-cost agents; root owns orchestration and final integration.

## Scope

- `compset/static/dual-workspace.js`, `dual-workspace.css`, new scoped map helper files if necessary, `index.html` only for required asset loading.
- Focused UI/map tests in `tests/` and existing UI regression checks.
- `docs/market-studio-research.md`, `docs/market-studio-design.md`, `docs/dual-workspace-contract.md`, `docs/design/market-studio-concept.png`, this order, `handoff/reviews/032-market-studio-redesign.md` and `handoff/reviews/032-market-studio-map-review.md`.
- Read-only Yellow UI references and official vendor documentation; local browser acceptance on the existing requested URL `http://127.0.0.1:8765/`.

## Ownership

- Map implementation agent: dual-workspace.js and map helper/test files only; root waits for ownership handoff before shell integration.
- Visual implementation agent: dual-workspace.css and docs/market-studio-design.md only.
- Research agent: docs/market-studio-research.md only.
- Root: index.html, final JS integration after map handoff, review and executable verification.
- Visual agent independently reviews and executes map JS proof after its CSS work freezes; it must not implement map fixes. Root reviews CSS and the integrated result.

## Requirements

Preserve STR/hotel modes, source/context guards, existing collection controls and truthful evidence semantics. Add precise editable geographic polygon selection alongside circle selection, explicit apply/cancel/clear and visible match counts. Map/table filtering and named local selection workflows must not silently change saved eligibility or start collection. Keep unavailable distinct from booked and unknown distinct from zero. No new paid products, provider calls, rate publication, database changes, proxy/phone modifications or fabricated vendor parity.

Use Yellow's compact action ribbon, deliberate typography, quiet pale surfaces, yellow selection accent, dense readable tables and detail inspectors. Compare reference modules and map patterns before claiming completeness. Record implemented versus data-dependent capabilities. Verify behavior, saved-data regression, responsive rendering and live assets separately.

Founder follow-up: carry Yellow's actual compact table/ribbon structure into the workspace and expand the hotel calendar/table so recorded room/rate-plan, meals, cancellation, payment, tax/fee, party and observation details are discoverable from each date without implying unavailable source coverage. Preserve the complete recorded source offer list and exact stay context. Yellow's reservation calendar style may inform navigation; it does not establish an Airbnb OTA feed or permission to alter Yellow domain code under this order.
