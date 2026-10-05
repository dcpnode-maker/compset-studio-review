# CompSet Studio: independent handover

Prepared 28 September 2026. This is a local review package, not an execution dispatch.

**Latest delivery state:** UI responsiveness changes are independently reviewed and committed as `219b840`; root executed all 78 JavaScript tests with real saved data and zero skips. Android **0.1.3** is installed on the OnePlus 10R: a verified, authenticated Wi-Fi neutral HTTPS probe passed, and visible Stop closed an active verified TLS connection and removed the service/listener. A later cellular attempt confirmed the selected Android transport but failed at DNS64 validation; no cellular egress or distinct IP was established. The phone was left stopped. Other-device proof remains outstanding. Updated dashboard runtime activation, browser visual acceptance, the requested design-reference attribution and complete compset prices remain outstanding.

## Scope and profile

- Project: `C:\Users\astha\CompSetStudio`, a standalone application separate from Yellow.
- Scope: the STR and hotel dashboards, saved comparison datasets, collection pipelines, tests, and remaining delivery work. The Android gateway has bounded Wi-Fi proof and a separate remaining cellular/cross-version verification workstream.
- Profile: `independent-review`. Inspect evidence and assess readiness under the receiving environment's actual controls. This document does not authorize overriding a rejected operation, changing approval settings, or treating a second model's opinion as execution permission.
- User's desired outcome: the updated local dashboards and comparison views are usable, with honest coverage and verified fresh-data controls.
- No receiving harness has been launched or messaged by preparing this package. No restart, browser inspection, collection, or device action is dispatched by it. The source thread's separately authorized physical-phone tests are documented below.

## Source and local data

Implementation commit: see the exact `implementation_commit` in `manifest.json`, on `codex/hotel-portfolio-otas`. The manifest records tracked implementation files and their current working-file SHA-256 hashes, plus local data locations. It excludes this handover directory to avoid self-referential hashing. It is an integrity inventory, not executable instructions. UI baseline work is in `b0a34cf`, the responsiveness follow-up in `219b840`, and the reviewed Android follow-up in the manifest's implementation checkpoint.

The existing directory is the complete local working context. A fresh Git checkout alone does not include saved observations: `data/`, `routes/data/`, the virtual environment, SDK/build caches, and some build outputs are ignored. Preserve original observations and their timestamps. Do not erase or regenerate the database to make a test pass. Do not copy credentials, browser profiles, pairing tokens, or raw conversation logs into a remote service. This package contains pointers rather than exporting those materials.

Main components:

| Area | Entry points |
| --- | --- |
| Local server and read API | `compset/server.py`, `compset/intelligence.py`, `compset/workspace.py` |
| Dashboard shell and views | `compset/static/index.html`, `app.js`, `dual-workspace.js`, `dual-workspace.css`, `rates-workspace.js` |
| STR comparison construction | `compset/portfolio_compsets.py`, `docs/portfolio-compsets.md`, `docs/adaptive-comparison.md` |
| Hotel portfolio and comparison research | `compset/hotel_portfolio.py`, `hotel_memberships.py`, `hotel_compset.py` |
| Data and collection contracts | `docs/dual-workspace-contract.md`, `docs/workspace-collection-contract.md`, `docs/hotel-ota-pipelines.md` |
| Source and semantics guidance | `README.md`, `docs/airbnb-calendar-semantics-research.md`, `docs/one-adult-price-semantics.md` |
| Phone gateway | `android-gateway/`, `routes/owned_devices.py`, `docs/android-gateway.md` |
| Next-version master/node plan | `docs/gateway-master-architecture.md`, `handoff/orders/017-master-and-team-node-architecture.md` |
| Orders, delivery and independent proof | `handoff/orders/`, `handoff/delivery-2026-09-28.md`, `handoff/reviews/` |

The project uses its own `.venv\Scripts\python.exe`; system Python is not the verified environment. The implementation is Python/Scrapling/Playwright/SQLite with plain JavaScript and CSS. No framework migration is required for this handover.

## Current runtime and the unresolved rejection

Read-only verification on 28 September found a responding old server at `http://127.0.0.1:8765`, PID 9464, owned by the user and launched by the project's virtual-environment Python. These are observations, not identifiers to act on later without rechecking.

- `/api/status` returned 200 and `idle`.
- New intelligence/workspace routes and workspace assets returned 404. The existing HTML references new assets, so the mixed old server/new files state is not accepted as a working UI.
- The ordinary launcher reuses a responding server; opening it again does not load the new route table.
- Independent review found no documented shutdown API, restart command, service manager, or hot reload for the hidden running process. Console Ctrl+C is supported when the server has an accessible console.
- No active collection lease was observed. The latest collection job was partial.

Three recorded local restart commands were rejected before execution by automatic tool approval review with the sole reason `blocked by policy`. They checked server identity and idle status; the evidence does not support blaming an indiscriminate process-kill command.

| UTC timestamp, 28 September 2026 | Tool call ID |
| --- | --- |
| 00:36:47 | `call_LILsb0xldBaJSPP5yVOCc4dt` |
| 03:03:01 | `call_wJTfvY5Sap4QwlHuIKGvq6Vq` |
| 07:30:27 | `call_pyi8wmY4OkqqDcTUvQeNRbAX` |

No specific rule or diagnostic cause was supplied. A tool bug has not been established, and a blanket prohibition on every possible app restart has not been established either. `handoff/reviews/015-order007-live-delivery.md` reports that a CUA request was rejected by browser URL security policy; it provides no tool-call or session ID. This handover review independently located the shell rejection evidence, not the original browser call, and does not attribute the shell's generic message to that browser event. Browser acceptance remains unverified.

A later founder-authorized normal restart attempt on 28 September did not reach the restart step: its read-only preflight (source/launcher inspection, current listener identity and status) was itself rejected before execution with the same generic `blocked by policy` result. No restart occurred from that attempt. Separately completed GET diagnostics returned 200 for `/` and `/api/status`, and 404 for `/api/workspace`, `/dual-workspace.js` and `/dual-workspace.css`. The user has clarified that the current purpose is educational GPT/Claude benchmarking, with commercial use deferred; that purpose was not identified by the tool as a rejection reason.

Reviewing these facts is permitted work. This package intentionally contains no script or queued instruction to repeat the rejected action through a different provider, process, port, or harness. Any execution decision requires a legitimately permitted path under the environment's controls. Do not report activation based on source tests or another model's agreement.

## Existing data and its limits

| Dataset | Saved coverage | Remaining limit |
| --- | --- | --- |
| BnBMe direct catalogue | 113 returned ACTIVE properties: Dubai 67, Riyadh 35, London 11 | Covers the returned catalogue, not an independently verified corporate total; direct-site rates are not Airbnb rates |
| Airbnb host inventory | 60 separately namespaced listing records | Identity links to direct properties remain unverified |
| STR comparisons | 173 subject comparison records against 374 exact-ID candidates | Not 173 complete compsets; Riyadh/London candidate gaps and missing source attributes remain |
| Saved Dubai sample | 67 selected competitors; 2,010 calendar cells observed in the dated window | Calendar availability is distinct from a nightly price; search was bounded and partial |
| One-night pricing | 2,040 planned cells: 2 quoted, 1,582 source-restricted/skipped, 456 unknown | Restricted dates do not prove booked nights; exact price coverage is incomplete |
| Aketa comparison research | 70 retained source features/properties; six evidenced peers within 10 km | No collected dated rates for those competitors |
| Latest bounded Aketa refresh | 72 offer observations; 32 indicative cells, one unavailable, 117 unknown out of 150 | Zero exact quotes established by that run; this proves the CLI path, not the dashboard button |
| Imported Lighthouse portfolio | Six exact subject identities, 42 name-only competitor memberships | Names are not verified competitor OTA identities; no invented rates or automatic adapter links |

All counts describe saved evidence. Preserve source dates, party, currency, taxes/fees, amount basis, and availability semantics. Missing data stays unknown. Do not equate unavailable with booked, rounded/indicative values with exact quotes, or a saved comparison record with a complete compset.

The dashboard's STR fresh action targets the saved Dubai Airbnb comparison set, not every direct-site property. Aketa is the supported hotel collector. Imported hotel profiles without linked adapters correctly disable fresh collection. Viewing or reloading saved evidence must not begin a collection job.

## Verification already recorded

These are separately recorded proof scopes; preparing this handover does not rerun or extend their acceptance:

- Full Python suite: 568 passed; final focused backend/HTTP/reviewer checks: 30 passed.
- Complete JavaScript suite with actual saved projections after Order016: **78 passed, zero skips**; root executed this follow-up suite.
- Independent reviews: `handoff/reviews/021-*` through `029-*`; consult each file for exact scope and proof.
- Warm projection medians approximately 18-21 ms; first summary approximately 1.2 seconds. These exclude HTTP, browser, and source-network latency.
- Order016's offline DOM-construction fixture: initial mobile elements created fell from 3,884 to 561; map edits retain the existing map/tile instance and zoom. This measures DOM work in the test harness, not browser latency or a performance comparison against commercial products.
- Android 0.1.3 build/lint and v1/v2 signatures passed; 181 implementer core assertions, 456 new independent DNS64 checks and 101 independent gateway assertions passed. Desktop phone client: 21 tests from the earlier checkpoint, including isolated real TLS tests.
- APK SHA-256: `249187863bb59fe39196431737b0ac73508f5b766c1c4b2e0215291bf1a2e88e`.

The independent reviewer personally verified a physical TLS1.2 handshake, mandatory certificate-chain validation and the exact pairing pin on the OnePlus 10R. Root then installed 0.1.3 and observed the Wi-Fi selector before a successful authenticated neutral probe at 12:49 UTC, with proxy and destination TLS verification and one 1,785.86 ms sample. Root's visible Stop closed a newly verified TLS connection in less than four seconds; a follow-up found no foreground service and an unreachable listener. The final button-disabled UI assertion was interrupted when the app left the foreground.

The subsequent 13:13 UTC cellular test confirmed matching selected/running handles and Android's cellular/internet/validated/not-VPN capabilities, with Wi-Fi ingress retained. The single neutral request failed when the duplicate-only DNS64 helper rejected its response. The phone advertised /96 translation; no exact offending address or successful egress was captured. No public-IP comparison is possible. Its visible Stop closed an unauthenticated verified TLS connection in 162.83 ms; service/listener teardown passed and the final button-disabled assertion was again interrupted. Cellular compatibility needs repair and retesting. Mid-transfer authenticated Stop, long sessions and other Android versions remain unverified. Details and executor attribution are in review029. These neutral tests do not establish accommodation-source access or activate a collector route.

The user-requested KoelJain resources have not been identified; an exact reference has been requested. Checked-in design concepts (`docs/design/str-desktop.png`, `hotel-desktop.png`, `mobile-workspaces.png`) are not screenshots or proof that those resources were used. Actual visual acceptance remains open.

Order017 records the next-version architecture: the user selected their online Windows laptop as master for opt-in team phone nodes, with visible persistent operation and separately verified network routes. Independent Android research identified API/permission, multi-SIM and foreground-lifetime limits; the architecture preserves them. This is planning only: no master service, remote endpoint, multi-route APK, enrollment or new collector routing is deployed. Cellular DNS64 repair remains a prerequisite. Usable routes and distinct public exits are separate counts.

## Deferred delivery

An hourly thread heartbeat named **CompSet handover when harness is ready** (ID `compset-handover-when-harness-is-ready`) waits for explicit readiness evidence from the existing universal-harness owner chat, **Design RMS model selection flow**. It is authorized to give that chat this local package for independent review, preserve the unresolved rejection and missing-data limitations, and pause after confirmed delivery. It is not authorized to repeat the rejected activation through another provider or alter approval controls. Creating the heartbeat is not proof that delivery or harness readiness has occurred.

## Evidence required before calling delivery live

These are acceptance criteria for a legitimately authorized environment, not a queued activation task:

1. Prove which source revision the serving runtime has loaded; confirm the new intelligence APIs and dashboard assets respond successfully.
2. Check STR and hotel navigation, property isolation, calendar/table/map views, unknown states, comparison decisions, details, exports, desktop and mobile layout.
3. Verify that saved-data navigation issues no collection mutations. Test fresh/pause/resume separately only under an authorized collection scope, retaining the selected job identity and truthful partial failures.
4. Report source implementation, runtime activation, visual acceptance, and dataset completeness separately. A newly running UI cannot make missing competitor rates complete.

Open questions for independent review: what produced the unexplained tool rejection, whether the environment offers an established permitted lifecycle operation, and whether UI behavior matches the existing contracts after legitimate activation. No app, tool, or harness settings were changed by this handover.

## Portable source export

Order018 packages the complete tracked project for the user's independent review in another environment. The ZIP preserves source, tests, dependency declarations, existing launch/build files, third-party notices and docs. Its text companion is for reading source; binary images/assets are represented by paths/hashes there and retained in the ZIP. A separate source manifest records the exact exported working-file bytes, including line endings. This is not a database export, bundled SDK/virtual environment or an execution dispatch. Private live datasets, credentials and pairing material stay local. A local file link can be opened by a local harness; a cloud model needs the file uploaded or an appropriately accessible remote link.
