# Rate intelligence workspace

Open CompSet Studio at http://127.0.0.1:8765. **Rate intelligence** is the default view. It brings the saved evidence into a rate-shopping workflow: choose a dataset, browse dates, inspect offers, check coverage and export the current view.

If the local server was already running before this update, it must be restarted to load `/api/workspace` and the new static asset routes. Reloading the browser alone is insufficient. The attempted automatic restart was rejected by tool policy on 28 September 2026, so activation on the existing runtime remains pending. The original tabs remain usable in that runtime.

## Working with the view

1. Choose **Aketa** for the five hotel source rows, or the **Airbnb comparison set** for the subject and selected competitors. Their currencies and guest contexts remain separate.
2. Move through seven-day windows and switch between calendar grid and list. Source and evidence-state filters change the displayed saved observations; they do not request new dates or change the original guests.
3. Open a date cell to inspect its state, observation time, original context and every retained offer. Room, meal, cancellation, membership, coupon, tax and fee conditions remain attached when observed.
4. Inspect competitor eligibility and exclusion reasons, source diagnostics and duplicate OTA profile identities. An indexed profile or public `ACTIVE` property is not proof of current sale availability.
5. Export the visible filtered date window to CSV. **Reload saved data** reloads local evidence only.
6. Select **Fetch fresh data** to start a bounded collection job for the selected dataset. Its progress panel shows the actual dataset, dates, guests and collection phase. **Pause collection** takes effect between source operations; **Resume collection** continues eligible work using validated checkpoints. The saved view reloads when the job ends.

Fresh collection uses the next 30 dates in the property's local timezone. Aketa uses one adult, one room, no children and INR; the saved Dubai Airbnb set uses one adult, no children/infants/pets and its configured currency. The saved competitor membership is preserved. Source/search/state filters are display controls and do not change the live job. Switching the displayed dataset also does not retarget an active job.

Only one dashboard collector can run at a time. Jobs have finite request budgets, paced source calls and a time limit. A budget ending or a blocked source can leave a partial result; neither means all prices were collected. Fresh mode requests eligible source observations, while respecting source access stops and cooldowns. Resume can reuse matching fresh evidence. Refreshing prices does not create the missing competitor sets for every portfolio property.

## Reading the cells

| State | Meaning |
| --- | --- |
| Quoted | An exact contextual amount supported by saved request/response evidence. It is an observation, not a booking guarantee. |
| Indicative | A calendar minimum, rounded display or other observed amount without a verified equivalent checkout total. |
| Unavailable | Source evidence rejects that particular stay/context. It does not establish that every room or night is booked. |
| Restricted | A stay-length, arrival or departure rule prevents the requested stay. |
| Unknown | Evidence is absent, incomplete, blocked, malformed or does not match the requested context. It is never a zero price. |

Google calendar displays and its separately observed partner offers remain distinct. Abbreviated prices retain display text without inventing exact numeric values. The headline for an OTA can be its lowest observed offer for that stay and party; different room and rate-plan conditions are visible in the detail. This is not a like-for-like parity calculation.

## Initial evidence loaded on 28 September 2026

| Dataset | Coverage |
| --- | --- |
| Aketa | 150 source/date cells: 31 indicative, 1 contextual unavailable, 118 unknown; 51 offer observations and 8 audited OTA profiles. |
| Airbnb | 68 listings, 2,040 planned date cells: 2 quoted, 790 overnight unavailable, 792 stay restrictions, 456 unknown. |
| Candidate evidence | 316 candidates, including 67 selected competitors; original search context and incomplete discovery remain explicit. |
| BnBMe portfolio | 113 public properties: Dubai 67, Riyadh 35, London 11. 60 Airbnb listing records have no explicitly verified link to the direct-site property IDs. |

This is not a complete BnBMe company inventory or a complete set of all its properties' competitors. Only one Dubai subject currently has a saved competitor set. Aketa has observations of its own distribution profiles and zero collected competitor hotels. BnBMe direct-site evidence includes 62 dated stay prices, 98 display prices and 41,245 calendar records; 8,604 calendar records are unknown. These price bases remain separate from Airbnb quotes.

These counts describe saved evidence, not continuous live coverage. Source observation times are preserved when the projection is rebuilt. The generated-at time is not a new shop time.

## Reference and current limits

The authorized Lighthouse account was accessed read-only on 28 September 2026. Its Overview and Rate Insight workflows informed the property/context controls, date navigation, source freshness, calendar-to-detail flow and explicit distinction between rate restrictions and sold-out states. Reference account data was not imported into Aketa or BnBMe. Lighthouse branding and credentials are not included in the application.

This release supports saved rate shopping, inspection and exports. Aketa currently has source comparisons for one hotel, not a verified hotel competitor set. The Dubai Airbnb set is separate. There is no invented market rank, median competitor price, occupancy, demand forecast, rate recommendation, like-for-like parity score or PMS integration. Those depend on additional matched evidence and verified integrations. The user-facing view explains the comparability limit.

Lighthouse's [official product description](https://www.mylighthouse.com/platform/pricing) provides broader product context. An [official API](https://api.mylighthouse.com/) exists, but this build has no verified API entitlement or configured API integration. Portal access is not assumed to grant API access.

## Technical operation

`GET /api/workspace` projects fixed saved inputs through `compset/workspace.py`. It does not accept an arbitrary file path, call a remote site, launch a job or write to the evidence database. The server reuses a projection until an input file revision changes. Public property links are allowlisted and stripped of query strings; arbitrary raw response objects and session headers are excluded.

Collection is an explicit separate POST workflow: `/api/workspace/collect` starts, `/api/workspace/job` reads progress, and `/api/workspace/pause` requests a cooperative pause for the current job ID. The fixed dataset contract cannot accept arbitrary commands or source URLs. Details are in [the collection API contract](workspace-collection-contract.md). Starting or reloading the dashboard does not start collection.

The UI renders data as text, contains wide tables within their scroll region, exposes pure data helpers for Node checks and protects CSV cells against spreadsheet formulas. Python tests cover source context, restrictions, planned-cell coverage, malformed inputs and read-only HTTP behavior. Independent projection review is recorded in `handoff/reviews/019-rate-workspace.md`; collection lifecycle, fresh/resume transport and UI proof are in `handoff/reviews/020-workspace-collection.md`.

Local browser inspection was not repeated after the earlier automatic browser safety rejection for localhost. Functional verification uses Python, local HTTP and Node; it does not establish a visual browser QA pass.
