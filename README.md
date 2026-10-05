# CompSet Studio

A standalone local rate-intelligence workspace for hotels and holiday homes. Built in Python with **Scrapling 0.4.15**, its **Playwright** browser fetcher, direct HTTP replay, SQLite and plain HTML/CSS/JavaScript. No AI model or API subscription is needed to run it.

## Open the dashboard

Double-click `Start-CompSet.cmd`, or run `Start-CompSet.ps1`. The dashboard is served at **http://127.0.0.1:8765**. The new default workspace has **Short-term rentals** and **Hotels** modes. STR provides a portfolio multicalendar, city/bedroom/source filters, per-property comparisons and maps. Hotels provides Aketa's rate calendar/table, source and offer-condition filters, and separate hotel product/service comparisons. The six imported Lighthouse subject profiles retain their own identity and coverage. Both modes include source timestamps, details and CSV export. Mobile uses a focused list/day layout, bottom navigation and detail sheets. See the [dual-workspace contract](docs/dual-workspace-contract.md) and [design notes](docs/dual-workspace-design.md).

**Fetch fresh data** starts bounded collection for the selected dataset, with visible progress and cooperative pause. **Resume collection** reuses eligible fresh checkpoints and continues missing work. **Reload saved data** remains a separate local read. Collection uses the supported one-adult, next-30-day context shown beside the job, independent of grid filters. Airbnb refreshes the saved set's calendars before one-night prices; Aketa runs its configured source adapters. Access failures remain visible gaps.

**Collection tools** opens the retained detailed workflows: the Property portfolio view has Dubai/Riyadh/London inventory controls; Competitor research accepts an Airbnb subject and map circle; Saved prices retains planned-date evidence and original exports. Viewing or reloading saved evidence never starts collection. The local server starts one collection job at a time. The STR fresh button currently targets the saved Dubai Airbnb comparison set; it does not claim to refresh all 113 direct-site properties. Imported hotels without linked OTA adapters have a disabled fresh action.

**Existing running server:** restart CompSet Studio to load the new workspace API and assets; a browser reload alone is insufficient. Automatic approval review rejected the prior restart/browser inspection with the generic reason "blocked by policy". Activation and browser visual verification remain pending on the previously running server; offline tests are not a substitute for either.

The local environment is already installed on this computer. On another Windows computer with Python 3.10+ and Chrome, run `Setup-CompSet.ps1` once. The setup installs only into this project's `.venv`. If Chrome is not installed it attempts a Playwright Chromium download.

## Current BnBMe inventory

The official public catalogue returned **113 properties: Dubai 67, Riyadh 35, London 11**. All 113 corresponding public detail responses report `ACTIVE`. This establishes coverage of the returned catalogue, not an independently verified corporate inventory total. Local evidence also contains all **60 listing links currently shown on Laya's public Airbnb profile**, with cached listing attributes. Airbnb channel identities remain separate from direct-site property IDs until an explicit cross-reference verifies a match.

The direct website returns daily calendar rates and unit availability counts. Its dated charge-breakdown request provides separate stay totals and fees. The captured calendar covers 1 September 2026 through 31 August 2027; observations are current snapshots of returned source data, not a reconstructed booking history. Empty inventory placeholders (`inventory_uuid: null`, zero counts/prices) are **unknown**, never free prices or proven unavailable nights. Direct-site prices are not Airbnb prices.

All public catalogue/detail attributes, descriptions, amenities, image/floor-plan references, native currencies, price context and source evidence are retained. AED/SAR/GBP stay separate; there is no implicit currency conversion. Missing floor area, verified building classification and unobserved Airbnb hosts remain unknown. Marketing words do not establish a quality grade.

The saved comparison projection now covers 173 separate subject records (113 direct and 60 Airbnb) against 374 exact-ID Airbnb candidates with retained observation history. It preserves missing attributes and every selection/exclusion decision. Riyadh and London still lack regional candidate coverage, and most direct-site subjects lack explicit accommodation-privacy evidence. These comparison records are not 173 complete compsets. Aketa's separate local research retains 70 source features/properties and selects six evidenced product/service peers within 10 km; those peers do not yet have dated OTA rate datasets.

All six visible Lighthouse subject profiles are imported under exact namespaced IDs. Their current account-table comparisons supply 42 name-only competitor memberships. Competitor OTA IDs, prices and availability are not inferred from those names. Account artifacts stay under ignored `data/hotel-portfolio/`; no credentials are saved in them.

## Airbnb observations

- Listing title, capacity, room/property type, location and room counts when present in observed public source data.
- Dated calendar availability, check-in/check-out restrictions and minimum/maximum stay lengths.
- Nightly calendar price fields **when Airbnb returns them**. Null is retained as unknown.
- Dated stay quotes, including selected/alternative rate options when returned. Rounded display prices are distinct from exact option totals.
- Collection context, source paths, timestamps, raw public JSON, hashes, coverage and warnings.

The first verified property is [BnBME's Act One / Act Two 1BR listing](https://www.airbnb.com/rooms/1567889913136387224). The initial candidate 1452665697263519565 returned HTTP410 and was replaced; its failed observation is retained as evidence.

**Unavailable does not mean booked.** The calendar does not tell us why a date is unavailable. Prices are contextual: dates, guests, cancellation option, currency and taxes/fees matter. A stay-total average is not a true nightly calendar rate. This build does not invent nightly prices when the calendar returns null.

The [calendar research note](docs/airbnb-calendar-semantics-research.md) combines official Airbnb guidance with a live guest-picker check. Disabled picker dates depend on whether the guest is selecting arrival or departure; an overnight-unavailable date may allow checkout. Calendar preflight checks sleeping nights on `[checkin, checkout)`, with separate arrival/departure and stay-length rules. Missing fields never establish unavailability. Exact business negatives are completed observations, not reasons for immediate identical retries.

## How collection works

1. Scrapling `DynamicSession` opens one anonymous listing page using installed Chrome/Playwright.
2. It observes public JSON requests and opens the actual date-picker control.
3. Scrapling `FetcherSession` replays observed, allowlisted read requests, preserving their current persisted-query hashes. A calendar request's observed month/year/count variables are adjusted to the chosen window.
4. Typed normalization records what the responses prove; missing fields stay unknown.
5. SQLite stores history and the latest snapshot is exported to JSON and CSV.

Request/session headers stay in memory. No booking, payment, host-message or account actions are performed. Access limits stop collection. Airbnb's endpoints are undocumented; schema changes or access restrictions are reported as gaps rather than successful extraction.

## Commands

From this folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m compset serve
.\.venv\Scripts\python.exe -m compset run --listing 1567889913136387224 --checkin 2026-10-17 --checkout 2026-10-20 --currency AED --adults 1 --days 30
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Update example stay dates if they are in the past. Defaults use Dubai's current date. Calendar windows include the start date and exclude `end_date`.

Observe the saved comparison set for **one adult and the next 30 Dubai calendar dates**:

```powershell
.\.venv\Scripts\python.exe -m compset nightly-monitor --max-listings 100 --request-budget 100 --interval-seconds 3
.\.venv\Scripts\python.exe -m compset nightly --source data\runs\<one-adult-run-id>\source.json
```

The nightly monitor uses one fresh browser bootstrap, then serial calendar reads with a reusable session. Its budget counts competitor reads; bootstrap traffic is reported separately. Fresh, complete calendar observations are reused for six hours after validating their context, rows and parser revision. A missing nightly price does not trigger an identical retry. Create `data/pause-nightly.flag` to pause between reads; remove that flag and repeat the command to resume. Run only one CLI collector at a time. These commands are separate from the dashboard's older calendar/stay-quote monitoring button.

`data/nightly-monitoring-latest.json` records per-listing run IDs and coverage. Each `data/nightly/<run-id>/` contains `nightly.json`, `nightly.csv` and `stay-quotes.csv`. `nightly_amount_for_requested_party` requires an observed one-adult source request; `calendar_display_amount` is separate. Fees, tax inclusion and per-adult modifiers remain null unless established by the source. Existing two-adult observations are preserved. See [price provenance](docs/one-adult-price-semantics.md).

The 28 September 2026 live batch observed all **2,010 calendar dates across 67 selected competitors** for 28 September–27 October: **1,242 available, 768 unavailable, no unknown dates**. Calendar responses contained **zero nightly amounts**. Availability coverage is complete for that selected window; one-adult nightly price coverage is not. Comparison membership came from the saved candidate search, whose original two-adult discovery context and partial search coverage remain attached. This batch does not claim a new exhaustive one-adult search.

Collect contextual **one-night stay totals** after applying fresh calendar restrictions:

```powershell
.\.venv\Scripts\python.exe -m compset one-night-monitor --request-budget 100 --interval-seconds 3
```

This job covers the subject and selected competitors for the next 30 dates. It skips only source-proven overnight, arrival, departure or stay-length failures; a minimum-stay failure does not establish that the night is booked. It bootstraps a fresh observed `StaysPdpSections` read-only POST, verifies its actual dates, guest counts, listing and currency, then uses a reusable session and serial requests. Request bodies and headers stay in memory. The finite budget counts direct follow-on quote requests; the one browser bootstrap and its bounded read replays are reported separately. Zero budget performs only local planning. `data/pause-one-night.flag` pauses between reads. Fresh quotes are revalidated from raw evidence before reuse; access failures or missing price semantics stop the job.

`data/one-night-latest.json` records progress, skip reasons, parser hash and provenance; `data/one-night-prices.csv` retains every requested date, including unrequested and unknown cells. Exact quotes append to SQLite observations as `one_night_quote`; each parser revision also appends `one_night_quote_revision:<parser-hash>` without replacing older evidence. Fresh saved responses are reparsed locally after parser changes, including earlier unknown results. A one-night stay total is not automatically a base nightly rate. Rounded display amounts never replace precise totals, and taxes/fees/cancellation remain unknown unless explicitly returned. These commands do not replace the dashboard's older monitoring button.

The saved 28 September price job represents **68 listings and 2,040 date cells: 2 quoted, 1,582 calendar-skipped and 456 unknown**. The source-proven skips comprise 790 overnight-unavailable stays, 727 minimum-stay failures, 60 disallowed arrivals and 5 disallowed departures. The final browser bootstrap timed out before receiving Airbnb data; a bounded connection diagnostic also timed out. The job stopped, preserved earlier evidence and did not relabel failed reads as unavailable. It has not completed one-night price coverage. Repeating the command resumes eligible work with fresh context checks when the source is reachable.

The follow-on hotel is [Hotel Aketa, Rajpur Road, Dehradun](https://www.google.com/travel/hotels/entity/ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ). Its [source plan](docs/hotel-aketa-source-plan.md) records the verified Google Hotels calendar and parser. One adult and zero children were observed in the selected traveler controls. One room was requested, but the displayed room count remains unverified and is stored as null.

The saved Google capture covers **all 30 one-night calendar dates, 28 September–27 October 2026**, in INR. These are indicative calendar minimums: 25 integer displays and 5 abbreviated amounts with no exact numeric price. Separate partner observations for 28–29 September preserve displayed supplier, room, meals and cancellation information when present. None is represented as a verified supplier checkout quote; tax/fee inclusions remain unknown. The dated MakeMyTrip page returned an unusable response, so it did not establish a price or sold-out date.

Hotel evidence is under `data/hotels/aketa/`: `latest.json`, `rates.csv`, `calendar.csv` and timestamped source captures. Reparse a saved capture locally, or perform one bounded live Google calendar read:

```powershell
.\.venv\Scripts\python.exe -m compset.hotel_aketa --source data\hotels\aketa\google-form-canary-complete-2026-09-28.json --start-date 2026-09-28
.\.venv\Scripts\python.exe -m compset.hotel_aketa --live --start-date 2026-09-28
```

For a live read, replace the date with the current date in `Asia/Kolkata`. The collector uses one reusable browser visit and observed form controls; it does not make 30 separate requests when the calendar supplies the month in one read. Control/schema drift and access failures stop the read. Offline parsing keeps the capture's original observation time.

## Aketa across major OTAs

The [OTA pipelines runbook](docs/hotel-ota-pipelines.md) covers Aketa's source registry, bounded jobs, cache/resume, raw evidence, append-only SQLite history and source/date coverage. The saved-price source filter separates Google Hotels, Agoda, MakeMyTrip, Booking.com and Expedia.

Google supplies the indicative calendar. Agoda now supplies actual observed room-grid JSON for the selected stay, with per-offer occupancy, before-tax nightly displays, meals, cancellation, payment, membership and coupon conditions. The one-adult parser excludes returned two-adult alternatives while preserving them in raw evidence. Booking.com and Expedia currently provide blocked-source diagnostics; their exact-stay quote parsers are not yet verified. MakeMyTrip retains its unusable dated-response diagnostic. These gaps are explicit rather than fabricated sold-out dates or prices.

```powershell
.\.venv\Scripts\python.exe -m compset hotels-init
.\.venv\Scripts\python.exe -m compset hotel-run --dashboard
.\.venv\Scripts\python.exe -m compset hotel-status
.\.venv\Scripts\python.exe -m compset hotel-run --live --sources google_hotels,agoda --request-budget 3 --dashboard
```

Without `--live`, runs only reparse fresh saved evidence. With `--live`, the finite budget counts adapter capture calls; a browser may make multiple internal requests. `data/hotel-pipelines/` contains `hotels.json`, `evidence.sqlite3`, `raw/`, `latest.json`, `rates.csv` and `coverage.csv`. Create `data/hotel-pipelines/pause.flag` to stop between operations; remove it before resuming. No recurring refresh is enabled. The current rollout supports Aketa only, one room, one adult, zero children, INR and thirty one-night dates.

Reparse saved evidence without network requests:

```powershell
.\.venv\Scripts\python.exe -m compset reparse data\runs\<run-id>\source.json
```

## Files and local API

`data/compset.sqlite3` holds run history. `data/runs/<run-id>/` contains `source.json`, `result.json`, `calendar.csv` and `quotes.csv`. `data/latest.json` identifies the current result. Raw data and the virtual environment are excluded from Git.

Inventory tables in the same database are `portfolio_snapshots`, `portfolio_properties`, `portfolio_hosts`, `portfolio_channel_listings`, `portfolio_links`, `portfolio_prices` and `portfolio_calendar`. `data/inventory/<snapshot-id>/` contains full JSON, property CSV, host CSV, prices CSV and a daily calendar CSV. `data/portfolio-latest.json` points to the saved inventory. JSON/SQLite retain full raw detail observations; the property CSV omits bulky daily/raw arrays, available in their dedicated exports. Snapshots append; repeat import is idempotent.

The dashboard uses `GET /api/status`, `/api/portfolio`, `/api/compset`, `/api/latest`, `/api/health`, `/api/one-night`, `/api/hotels/aketa` and `POST /api/run`, `/api/discover`, `/api/monitor`, `/api/inventory-refresh`, `/api/inventory-pause`, with JSON and `X-CompSet-Request: dashboard-v1`. It binds only to `127.0.0.1` and rejects cross-origin collection requests. Saved-price reads use fixed paths and retain the local host/origin checks. Exports are under `/exports/`, including `one-night-prices.csv`, `one-night.json`, `hotel-aketa-rates.csv` and `hotel-aketa.json`.

Competitor discovery retains all returned candidates before filtering, including outside-circle and excluded listings. The saved audit contains 316 unique candidates and 67 selected physical matches inside 2 km. Search coverage is partial because of request/page limits. The target of 100 is not a completeness claim. [Adaptive comparison](docs/adaptive-comparison.md) relaxes secondary bathroom/capacity tolerances, then expands radius within 10 km, only at ten or fewer eligible matches and when source coverage permits. Exact bedrooms, accommodation type and the requested guest-capacity floor remain enforced. Search requests share one budget across expansions; expansion detail reads share a separate 200-read cap. The UI displays the applied stages and preserves every candidate decision. The current 67-match audit required no relaxation or expansion.

No hourly scheduler is enabled. Google Hotels and Agoda provide observed hotel prices with different precision/context; the other direct OTA sources remain incomplete as described above. The tool runs locally without Yellow. The handoff's rotating date samples do not promise hourly freshness for every date.

## Optional local proxy route tooling

The newer finite batch and owned-phone implementation are documented in the [phone/proxy guide](docs/proxy-pool-and-android.md). The batch found 100 successful neutral HTTPS probes out of 939 completed checks; a repeat canary passed 10 of 20. The native Android gateway targets Android 6+ with explicit pairing, certificate verification, foreground Stop and selectable session/data limits. Phone egress and OTA use require separate verification. The desktop owned-device registry remains separate from public proxies and does not change production collection routes.

The [routes runbook](routes/README.md) includes the five-source Kaggle batch validator, provenance manifest, SQLite health/sticky sessions, local HTTP/HTTPS CONNECT proxy, Docker configuration and an observed-request wrapper. Kaggle is only a batch worker; the laptop hosts the optional service. The checked-in pool ships empty. On 28 September, an authorized local probe tested 20 candidates: three passed HTTPS httpbin validation. The native loopback hub imported those three routes and started at `127.0.0.1:8080`, with background checks disabled. Its selected route then failed two bounded forwarding attempts, so end-to-end proxy usability is not verified. Live manifests and evidence are under `routes/data/`; normal collection stays direct. Docker was not started.

Validation defaults to eight workers with finite budgets. Sessions stay on their explicitly selected route; access blocks stop attempts and establish a cooldown. CONNECT uses asyncio streams and preserves end-to-end TLS. Current browser-observed requests supply operation hashes and headers. There is no historical hardcoded API key, guessed endpoint or automatic route switching after target blocks. Successful httpbin validation would establish only that probe's connectivity, not Airbnb compatibility. Proxy category remains unknown unless independently established. Normal CompSet collection continues using direct access; proxy tooling is an optional separate path.

## Efficient long sessions and changes upstream

Official inventory refresh uses one reusable HTTP session, a one-second minimum interval, finite budgets, six-hour cache/resume checks, per-property checkpoints and cooperative pause. Airbnb transport captures fresh anonymous browser requests, then uses bounded direct HTTP workers; session headers stay in memory. Listing attributes have raw and parser-versioned caches. Catalogue and listing identifiers deduplicate exact IDs; similar names never merge accounts. The UI parses/projects each saved inventory revision once and paginates rows.

New request hashes come from current browser traffic, never guessed hashes. `data/schema-health.json` records operation hashes, field fingerprints and semantic failures. A new hash may be used with the observed request template; a changed meaning is never approved automatically. Repair sequence: inspect retained source, capture one fresh read, update the typed adapter and a regression fixture, run contract tests, reparse saved data, compare a live canary, then resume. A changed schema can still require a developer correction; Scrapling is not a guarantee against semantic changes.

Import/reparse official evidence without network requests:

```powershell
.\.venv\Scripts\python.exe -m compset inventory
```

The dashboard controls call `inventory-refresh --request <json-file>` for fresh or resumed reads. Long jobs are bounded to one hour by the local server. Browser sessions are ephemeral and credentials are not persisted.

## Implementation and review

Architecture/integration and collection/parser work were divided into bounded lanes. GPT-6 Sol built the dashboard; GPT-6 Luna personally ran the independent test review. See `handoff/reviews/` for proof and limitations.

References: [Scrapling browser capture](https://scrapling.readthedocs.io/en/latest/fetching/dynamic.html), [direct HTTP sessions](https://scrapling.readthedocs.io/en/latest/fetching/static.html). Scrapling is BSD-3-Clause, not MIT as stated in the original handoff.
