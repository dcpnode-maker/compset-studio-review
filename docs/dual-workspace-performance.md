# Offline workspace construction measurements — Order016

These measurements count work performed by the deterministic Node DOM/Leaflet fixture. They do **not** measure browser layout, paint, network transfer, real map tiles, Lighthouse/PriceLabs latency or fresh OTA collection. Lower fixture construction counts are evidence of removed JavaScript/DOM work, not a quantified user-visible speedup.

## Before and after

The fixture contains 25 properties × 14 dates, a 390px viewport and 60 saved candidate map points. It mounts the real frontend module against fake GET responses, changes the selected mobile day, opens the map, sets zoom 16 and changes radius from 2km to 3km. The same instrumented harness can load the exact older module from Git without modifying the checkout.

Baseline source: `compset/static/dual-workspace.js` at commit `b0a34cfd02a855d37949a89b585b6dd0a898b49d`. Measurements were repeated on 2026-09-28; the construction counters were identical on repeated runs. The updated measurements apply to the current Order016 source; executable test assertions cover behavior separately.

| Measurement | Before | Order016 |
| --- | ---: | ---: |
| Elements constructed during initial mount, including discarded renders | 3,884 | 561 |
| Retained descendant elements after mount | 1,811 | 266 |
| Hidden desktop date-cell buttons constructed on mobile | 350 | 0 |
| Elements constructed for one mobile day change | 1,778 | 140 |
| Elements constructed for one map radius change | 371 | 25 |
| Map instances created across map open + radius change | 2 | 1 |
| Tile layers created across those operations | 2 | 1 |
| Map instances removed during that radius edit | 1 | 0 |
| Zoom after edit, starting at 16 | 13 | 16 |
| Intelligence requests during map radius edit | 0 | 0 |

Initial element construction decreased about 86%, and day-change construction about 92%, in this fixture. There is no latency percentage claim. The Node test runner also prints elapsed milliseconds; those values vary with scheduling and are deliberately excluded from this comparison. The local service's earlier projection benchmarks measure a different layer and are not combined with these counters.

## Reproduce without a browser, listener or network

Run from `C:\Users\astha\CompSetStudio`. Node and Git read local files only. The optional baseline loader requires an exact 40-character Git commit and benchmark mode; it does not check out files or modify the worktree.

```powershell
$env:COMPSET_DUAL_BENCH = '1'
$env:COMPSET_DUAL_BASELINE_REF = 'b0a34cfd02a855d37949a89b585b6dd0a898b49d'
node --test --test-name-pattern='repeatable offline' tests/test_dual_workspace.js

$env:COMPSET_DUAL_BASELINE_REF = $null
node --test --test-name-pattern='repeatable offline' tests/test_dual_workspace.js

$env:COMPSET_DUAL_REAL_DATA = '1'
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js tests/test_workspace_responsiveness_review.js
```

The last command additionally reads the actual saved projections with the repository's Python environment, then renders them through mocked fetches. It performs no source collection and launches no server. At final implementation freeze it passes **44 tests**: 33 standard frontend cases, one actual-data case, one benchmark, five retained reviewer regressions and four new reviewer-authored cases. New independent Order016 acceptance is recorded separately by its reviewer.

## Changes and preserved behavior

- Only the active responsive calendar is constructed. Day changes repaint only the daily rows. Desktop still displays the bounded 25-property/14-date grid.
- Hotel mobile presents readable rows for the selected date and source, preserving currency, amount basis, unknown/unavailable distinctions and offer inspection. Selected-day export has the same scope.
- A map edit updates existing layers and creates at most the first 25 quick-list buttons. Popup contents are lazy. The selected zoom survives; source/subject changes release the previous map.
- Identical pending GETs share one transport. Superseded requests are aborted; reload starts a new generation, and stale completion cannot remove or populate newer requests. Accepting a reloaded summary also invalidates reads/cache created by intervening navigation. Completed validated views use a 24-entry LRU cache. Revision, identity, date and normalized-filter guards remain in force.
- If reload replaces a removed subject, the new subject starts with its own observed center, default radius and first candidate page. A previous subject's dragged center and callbacks cannot affect the replacement.
- Mobile/tablet details contain keyboard focus and make the background inert. Desktop inspectors remain nonmodal. Reload/close restores connected focus.
- The persistent collection bridge remains untouched. Navigation, filter changes, day selection, map edits and reload perform no collection POST. An explicit collection keeps its original dataset/job identity.

## Remaining measurements and design work

Actual browser proof still needs permitted access: first usable view, cold/warm request timings, main-thread long tasks, layout/paint, real map pan/zoom, keyboard/screen-reader behavior, and screenshots at representative desktop/mobile sizes. No local-browser or runtime-activation restriction was bypassed for these results.

The shell still eagerly loads legacy/map code and serves static files with its existing cache policy; those files were outside this implementation scope. Source fetching remains dominated by provider/network behavior rather than these rendering changes. No language/framework rewrite, fabricated market metric, pricing write or automatic retry/fallback was added. Koel Jain's intended resource is still pending an exact verified link; no attribution is made.
