# CompSet Studio: STR, hotels and mobile

Original workspaces informed by authorized read-only inspection of PriceLabs multicalendar/reports and Lighthouse rates/overview. PriceLabs showed 143 account listings; these account records were not substituted for BnBMe source inventory. Lighthouse's configured hotel import is separately authorized under Order014. No pricing sync, paid rate refresh, account setting or subscription was changed.

## Visual specification

Concept references: design/str-desktop.png, design/hotel-desktop.png, design/mobile-workspaces.png. Root inspected all three images. The concept is a layout reference; saved evidence is authoritative for names, dates, prices, counts and states.

- White main surfaces, charcoal #202c35 headings, teal #076f73 actions, neutral #f7f8f8 navigation, thin #dce2e5 borders and modest corners. Use local/system sans-serif; no remote font dependency. Compact 26px desktop headings and 88px desktop STR cells keep evidence prominent.
- Desktop: narrow left navigation, compact contextual filters, calendar/table as primary surface, persistent collection area and a detail inspector. Source and stay context remain adjacent to prices.
- Mobile: 16px form input text, minimum 44px touch targets, day strip and property list, bottom navigation and sheet-style details. Map remains in normal page flow so subject/filter controls stay reachable; the touch canvas has at least 360px height. Dense desktop tables stay inside labelled scroll regions. Safe-area padding protects bottom navigation and sheets.
- STR loads subject headers first, then at most 25 properties by 31 dates; comparison decisions are paginated with compact map coordinates. Separate direct-site and Airbnb identity namespaces; studio bedrooms=0 remains valid.
- Hotels preserve source/date/room/meal/cancellation context and distinguish independent Aketa observations from imported Lighthouse profiles. Unknown price, unavailable stay, restricted stay and indicative display are different states.
- A single shared collection controller owns job polling, fresh/pause/resume and identity. Switching views or imported hotels never retargets an active job. Imported hotels with no collector disable fresh collection. Saved-data reload is read-only.

## Intentional concept corrections

Generated concepts contain illustrative facts that must not be copied into product data: incorrect 2024 STR dates, invented user avatar/name, stock property photographs, guessed source statuses, three illustrative hotel peers, split Act One/Act Two identity, and a misleading 113-property label on the saved Dubai Airbnb refresh dock. Code renders actual evidence, omits unsupported settings/help controls and photography, and labels the limited collection scope. No invented occupancy, revenue, demand or recommendation metrics are added.

## Kole Jain knowledge-base application — Order020

The founder's reference was found under **Kole Jain** in the Yellow knowledge base:

- `D:\Yellow\git-live-order611-source-v2\docs\design\KOLE-INTERACTION-SYSTEM.md`
- `D:\Yellow\git-live-order611-source-v2\docs\design\KOLE-RESOURCE-AUDIT-20260924.md`
- Canonical pointer: `C:\Users\astha\Documents\Codex\2026-08-14\cl\outputs\yellow\handoff\receipts\678-journey-first-kole-resource-audit.md`.

The existing study records 24 public lessons and links to [Kole Jain's resource catalogue](https://www.kolejain.com/resources). This implementation applies its compact hierarchy, aligned evidence tables, quiet surfaces, restrained color, persistent context, explicit feedback and accessible mobile controls. Numeric columns use tabular figures and right alignment. It retains only working controls; unsupported Sort/Group/Columns actions are not decorative placeholders. No creator-owned code, gated Figma files or assets were copied. Public lesson study is not a claim of component reuse rights or frame-by-frame visual review.

## Area interaction

Choose **Draw area**, press the desired center, drag outward and release. The map suspends pan/zoom during the gesture and captures the pointer. A minimum 8px movement prevents accidental taps. Choose **Move center** / **Resize area**, drag the corresponding 44px handle, or use the labelled radius number/slider (0.1–50 km). Escape, Cancel, pointer interruption, multi-touch and leaving the map retain the previous committed circle and restore the map's original interaction settings. Ordinary map clicks do not relocate it.

The circle shows its radius, geometric area, observed candidates, saved selection/provisional counts and missing decision/coordinate evidence. These are saved-candidate counts under the current decision filter, not a complete-market estimate. Candidate evidence and CSV retain source context. Editing the circle never invokes collection or rewrites saved match decisions.

## Verification ledger

Code-native interactions, pagination, filters, source semantics, exports and request/job races are exercised by Node/DOM and Python projection/HTTP tests. These tests do not establish visual fidelity.

On 28 September, GET-only diagnostics returned HTTP200 for `/dual-workspace.js`, `/dual-workspace.css` and `/api/intelligence`; the served JS contained the new Draw area control. No restart was performed. This updates the older 404 runtime observation without erasing the prior execution-denial history.

Browser visual and physical touch acceptance remain unverified. Previous local restart/browser inspection attempts were rejected as "blocked by policy"; no alternate browser/runtime route was used. The current proof exercises actual UI code in offline DOM/Leaflet fixtures and inspects CSS/contrast. It does not establish rendered viewport fit, browser latency or device gesture quality. Final source/HTTP checks and the independent findings are in `handoff/reviews/030-mobile-ui-map-area.md`.

Runtime status and artifact coverage are recorded separately in the implementation handoff. Runtime activation is not inferred from HTTP unit tests or static module availability.
