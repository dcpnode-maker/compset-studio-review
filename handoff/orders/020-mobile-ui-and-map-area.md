# Order 020: usable STR/hotel interface and touch circle selection

Status: IMPLEMENTED; independent source/DOM acceptance passed, 28 September 2026. Parent source checkpoint: `d85b4ac`. Live files are HTTP-verified; browser visual and physical touch acceptance remain open.

The founder requests a working CompSet Studio UI using the Koel Jain knowledge base in Yellow, retaining the basic PriceLabs STR and Lighthouse hotel workflows. They report that the map cannot draw a circle and explicitly require stable, easy touch drawing that reveals information about the chosen area. This is implementation, not a concept-image deliverable. The reference was found under Kole Jain in `D:\Yellow\git-live-order611-source-v2\docs\design\KOLE-INTERACTION-SYSTEM.md` and `KOLE-RESOURCE-AUDIT-20260924.md`; original code applies its documented public lessons without importing gated assets.

## Scope

- `compset/static/dual-workspace.js`, `dual-workspace.css`, `index.html`, and narrowly scoped integration adjustments in `app.js`/`style.css` only if required for the redesigned shell.
- Existing map/STR/hotel UI tests, a dedicated `tests/test_map_area.js` implementation proof and an independent `tests/test_map_area_review.js` plus focused UI reviewer proof.
- This order, `docs/dual-workspace-design.md`, `docs/dual-workspace-contract.md`, and `handoff/reviews/030-mobile-ui-map-area.md`.
- Read-only use of the referenced Yellow knowledge base. No Yellow source changes, raw knowledge-base/private-data export, backend schema changes, OTA collection, phone/proxy operations, model calls in the product or new frontend framework.

## Required behavior

Keep existing STR portfolio calendars, property/source/bedroom filters, selected property comparisons, hotel/source/offer filters, saved rate calendar/table, offer inspector, CSV export and scoped fresh/pause/resume controls. Preserve lazy reads, response identity guards, map instance/zoom reuse, mobile-only calendar construction and keyboard accessibility. All displayed data remains observed evidence with source/date/currency/party context; no fabricated revenue, occupancy, live quote, recommendation or completeness claim.

Add an explicit Draw area action with pointer events for mouse/touch/pen. Drawing temporarily prevents map pan/zoom interference, captures the initiating pointer, previews one geographic circle and commits on release. Escape, Cancel, pointer cancellation, leaving the view or teardown must restore controls and prior committed area. A second touch must not corrupt the active gesture. Preserve normal map pan/zoom outside draw mode. Provide a centre move handle, resize interaction and an accessible labelled radius control. Keep a clear radius/distance guide and visible selected-area summary of available candidates and their existing match decisions/observed attributes. Selection uses the observed candidate universe, not an invented complete market.

Drawing, moving, resizing, map navigation and viewing an area are read-only local interactions. They must not start collection, change saved eligibility, alter the selected subject identity or invoke a hidden scrape. Retain selected-area CSV and candidate evidence inspection. An explicit collection action, if reused, must keep its actual existing limited source scope and not imply an unsupported area collection job.

## Ownership and acceptance

Root owns visual/CSS/shell integration and final review; a bounded implementer owns circle interactions and their tests. An independent nonimplementer executes regression and adverse input/cleanup proofs. No conflicting edits to the same files. Preserve the untracked restart script and runtime logs without reading, executing or exporting them as test artifacts.

Acceptance includes existing full JS regression suite with actual local saved-data and benchmark flags when available, focused Python UI/API checks if integration changes, targeted pointer/mouse/touch/cancel/multi-pointer tests, context-preserving navigation/export proofs and independent review. Verify small-phone layout, reduced-motion, target size and contrast to the extent the actual permitted tooling allows; clearly distinguish source/DOM proof from live visual/device proof.

Do not repeat a previously rejected dashboard restart/browser action through another tool, port or provider. Do not claim activation, browser acceptance, Koel attribution or complete PriceLabs/Lighthouse parity without evidence. UI source delivery and the separate full-application acceptance under Order019 retain distinct statuses.

## Delivery evidence

Root and independent reviewer each executed109 passing Node tests with actual saved-data and benchmark flags enabled; root additionally executed21 passing Python intelligence/HTTP integration tests. The map benchmark retains one map, one tile layer, the selected zoom and zero map-edit data reads. These are deterministic construction/behavior checks, not browser latency measurements. Details and exact source hashes are in `handoff/reviews/030-mobile-ui-map-area.md`.

GET-only checks of the existing dashboard returned200 for the updated JS/CSS and intelligence API. Both static responses' SHA-256 hashes exactly matched the reviewed local files. Root performed no restart or browser inspection. A page already open before the change needs reloading to load the new controls.

C: reached zero free bytes while saving JS/CSS. Both files were restored from the known Git baseline and the scoped changes reapplied before complete tests and independent review. Regenerated bytecode/download cache was cleared. The founder's subsequent E: data request is separately recorded by Order021; it did not switch this source or the active data path.
