# Order020 independent mobile UI and map-area review

Date: 28 September 2026. Reviewer: Codex `/root/map_ui_review`, independent of the JavaScript and CSS implementers. Parent Git checkpoint: `d85b4acb8b8bb266ac78d5c4d91668eb4e21e59a`; reviewed changes are uncommitted.

**Outcome: source and offline DOM interaction accepted.** No remaining source/DOM blocker was found in this scoped review. Browser visual acceptance, physical device gesture quality, screen-reader behavior and browser latency remain **unverified**. This is not full-application acceptance under Order019 or complete PriceLabs/Lighthouse parity.

## Scope and independence

I read Order020, the implementation diff, current design/contract documents and the two existing Yellow Kole Jain references at `D:\Yellow\git-live-order611-source-v2\docs\design\KOLE-INTERACTION-SYSTEM.md` and `KOLE-RESOURCE-AUDIT-20260924.md`. The references support original compact neutral tables, meaningful controls, persistent context, approximately 16px mobile form text, 44px targets and reduced motion. No creator assets were imported or new public-resource research performed.

I authored only `tests/test_map_area_review.js` and this receipt. Root subsequently explicitly authorized adapting the reviewer-owned `tests/test_workspace_responsiveness_review.js` fallback-subject case from the superseded silent-click movement to an explicit captured Move center gesture. That case now first proves a custom center was committed, then proves replacement-subject reset and stale callback rejection. I did not implement JavaScript or CSS changes and made no commit.

No browser, restart, OTA collection, phone/proxy operation, external request, hidden scrape or product model call was used. The untracked restart script and runtime logs were not opened, run or exported. A repository search found no local PROJECT.md/AGENTS.md in CompSetStudio; the order supplied the bounded ownership and acceptance rules.

## Findings resolved before acceptance

1. **Stale release endpoint:** returning a draw/resize gesture inside the minimum radius could commit an earlier larger preview. The final release now validates the actual geographic/client endpoint, minimum 8px displacement and 0.1km radius. Independent actual-code proof verifies the prior larger draft cannot commit.
2. **Leaflet class erasure:** replacing the map element's complete className removed Leaflet's runtime classes. The implementation now replaces only owned editing classes. Independent mouse/touch/pen tests assert Leaflet container/touch/grab classes survive arming, preview, commit and cleanup.
3. **Invented decision:** a candidate with no selected/eligibility/status evidence displayed provisional in its popup. This was reproduced as a failing independent test. The popup now displays Unknown; independent proof covers the summary, popup and CSV without invented match decisions.
4. **Touch gesture setup:** direct map handles require pre-gesture touch-action:none. The final CSS applies it to the handles; explicit edit modes also suspend map pan/zoom before drawing.
5. **Small text contrast:** context-note text initially computed 4.47:1 on its specified background. Root changed it to the muted token; the final specified color pair computes 5.55:1. These are source-color calculations, not rendered browser measurements.

## Personally executed proof

```powershell
$env:COMPSET_DUAL_REAL_DATA='1'
$env:COMPSET_DUAL_BENCH='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:COMPSET_DUAL_BASELINE_REF=$null
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js tests/test_rates_workspace.js tests/test_root_workspace_review.js tests/test_workspace_responsiveness_review.js tests/test_map_area.js tests/test_map_area_review.js
node --check compset/static/dual-workspace.js
node --check tests/test_map_area.js
node --check tests/test_map_area_review.js
git diff --check
```

Result: **109 passed, 0 failed, 0 skipped**, duration **3041.472ms**. Syntax and whitespace checks exited zero. The actual-local-saved-projection case and benchmark case both appeared and passed; their flags were not merely set without registering the cases. The optional rates-workspace actual projection case requires COMPSET_WORKSPACE_FIXTURE, which was not supplied in this run; rates UI/collection regression used its deterministic fixtures. No physical browser performance conclusion follows from test-run duration.

The independent map suite contains **16 passing cases** executing the actual shipped module and its captured listeners through a fake DOM and Leaflet API. They cover:

- Mouse, touch and pen drawing; one reused geographic circle; initiating-pointer capture; prevented map propagation and exact restoration of every previously enabled/disabled map handler, touch action and cursor.
- Cancel, Escape, pointercancel, lostpointercapture, inside/outside second touch, hidden page, capture failure, non-primary input, right button, taps, foreign releases and minimum-radius endpoint rejection.
- Ordinary click preservation, direct center dragging, keyboard activation of resize intent, edge resizing, labelled numeric radius, navigation teardown, removed-listener cleanup and rejection of retained old callbacks.
- One animation frame for several previews, synchronous commit using the final release endpoint, cancellation of pending frames and rejection of manually invoked late callbacks after teardown.
- Committed-area CSV during an unfinished preview; exact subject/candidate identity, source URL, original observation, saved decision, spreadsheet formula guard and observed attributes in the evidence inspector. Saved fixture evidence remains unchanged and all fixture requests are GET.
- Missing decision evidence remains Unknown rather than provisional.

The existing suites independently rerun here retain STR property/source/studio filters and calendar context, hotel source/offer/day/table behavior, exact currencies and decimals, imported-hotel isolation, candidate paging/lazy detail reads, response identity/revision rejection, accessible modal focus handling and fixed collection-job identity. Explicit collection tests use mocked transports; the review itself performs no collection.

The benchmark reported this synthetic fixture: 25 properties x14 dates, 390px, 60 map points; 561 initial elements constructed, 266 retained nodes, 140 elements for a day change, 40 for a map edit, 1 map, 1 tile layer, 0 map removals, preserved zoom16, 0 map-edit requests and 0 initial desktop cells. These are deterministic construction counts, not browser latency or a speed comparison with another product.

## CSS and accessibility source assessment

The final source specifies 44px or taller buttons and map zoom controls, 44px Leaflet handle hitboxes, 46px mobile selects/search/radius input with 16px form text, visible focus outlines, labelled radius controls, aria-pressed edit state, polite status announcements, normal-flow mobile map content, scoped table scrolling, safe-area padding and reduced-motion rules. Candidate inspector and CSV provide routes to full observed evidence rather than implying complete market coverage.

Calculated contrast for the specified opaque pairs: muted text/white 5.82:1; context note 5.55:1; table heading 4.81:1; action/white 5.95:1; unknown state 5.60:1; indicative state 5.29:1; map status 7.30:1; focus outline/white 3.03:1. This targeted source audit does not claim every composited/browser state meets contrast or that a small-phone rendered layout has been visually accepted.

## Root diagnostics, separate from reviewer proof

Root reported separate GET-only HTTP checks: `/dual-workspace.js`, `/dual-workspace.css` and `/api/intelligence` returned200; served JS/CSS raw SHA256 matched the local files below. Root also reported its own109-test Node run and21 passing focused Python intelligence/server/root-route tests. I did not personally execute those HTTP or Python checks and do not present them as independent reviewer evidence. No restart or browser inspection was performed. Served-file equality supports availability of the source at the existing service; it does not establish rendered UI or physical touch acceptance.

## Reviewed file fingerprints

| File | SHA256 |
|---|---|
| compset/static/dual-workspace.js | fbcd6fc78361ce94683fe781fc0251372b1814d4be623855631e9888035e9f6e |
| compset/static/dual-workspace.css | 73a750588704a15ee2208def03c0534433e887e5a06f4b44b7ef3440d5fd3989 |
| tests/test_map_area.js | 5b3555f690db3fc3fee60127eb47136b405326c8e397541936ffa4802a60031f |
| tests/test_map_area_review.js | 852e555647787b1a09730173ca8644db62a1718477d1998cd35a8221542ee21d |
| tests/test_dual_workspace.js | 82b7a855619ac6ba5eef647f85344f52723253a87e22dc117c1a947ecf78401a |
| tests/test_workspace_responsiveness_review.js | 5d961b9ccab3e47e87c104dd9ab8323e0fe777ba49b1d96869c59d802d025dfe |

Scope excludes the separate data-drive relocation operation and full-application acceptance. The prior rejected restart/browser actions were not retried through another tool, provider or port. Browser/device limitations remain visible rather than being counted as passed gates.
