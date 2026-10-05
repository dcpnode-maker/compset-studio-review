# Hotel Aketa: implemented Google Hotels calendar and source evidence

Order: [007](../handoff/orders/007-one-night-price-evidence-and-hotel-follow-on.md). Standalone CompSet Studio only. Observed and exported on 28 September 2026.

## Current result

Google Hotels returned a full **30-date indicative one-night calendar**, check-in **28 September through 27 October 2026**, for **one adult, zero children, INR**. The calendar says **“Best prices for 1-night stay”** and the active price display says **“Nightly total”**. Each observed price belongs to its calendar date; missing cells are unknown, never unavailable.

The separate **28–29 September** date-form canary returned seven Google partner display observations. Examples:

| Google-displayed partner | Display amount | Visible product context |
| --- | ---: | --- |
| MakeMyTrip.com | INR 4,626 | Breakfast, 1 guest |
| Agoda | INR 6,066 | Breakfast, 1 guest |
| Booking.com | INR 11,730 | Superior Single Room, 1 single bed, breakfast, 1 guest |
| Booking.com | INR 16,567 | Deluxe King Room, 1 king bed, breakfast, 1 guest |
| Hotel Aketa official site | INR 9,609 | 1 guest; other inclusions unconfirmed |

Seven is a count of **display observations**, not seven unique room products: supplier summary cards and expanded room cards are retained separately, with their exact source descriptions. An explicitly two-guest Booking.com room was excluded from the one-adult rows.

These are **Google-displayed indicative prices**, not direct supplier checkout quotes. No booking, reservation, login, payment or external supplier visit was made. Requested room count is one, but the Google form does not explicitly echo a room count: `requested_context.rooms=1`, observed `context.rooms=null`, `context.requested_rooms=1`, and every rate has `room_count_verified=false`. Taxes, fees and their inclusions remain null. Calendar minimums do not establish supplier, room type, meals or cancellation terms. The page shows a cancellation-filter control but its state was not captured; no claim of an unfiltered supplier universe is made.

Five dates use abbreviated values such as `₹10.2K` or `₹12.7K`: `amount=null`, `approximate_amount=10200` or `12700`, `display_amount` preserves the original label, and `precision=abbreviated`. Other calendar values are `precision=displayed_integer`, still indicative rather than exact payable totals. No multi-night total was divided.

## Files and public contracts

- [Collector and parser](../compset/hotel_aketa.py)
- [15 parser, export and timezone tests](../tests/test_hotel_aketa.py)
- Saved source: `data/hotels/aketa/google-form-canary-complete-2026-09-28.json`
- Dashboard/data contract: `data/hotels/aketa/latest.json`
- Rate observations: `data/hotels/aketa/rates.csv`
- Date coverage matrix: `data/hotels/aketa/calendar.csv`

The result's `state=complete_indicative_calendar` applies to this calendar scope only. Its summary is 30 indicative dates, 30 calendar price rows, one partner-offer date, seven partner display rows, five abbreviated calendar prices, zero direct supplier quote dates, zero unavailable dates and zero missing calendar dates. It does not claim all suppliers, room types or cancellation plans were collected.

`rates` preserves check-in/check-out, requested/observed room count, adults/children/currency, `amount_type`, amount/approximation/raw display, precision, supplier, room name, meals, cancellation, inclusion unknowns and source provenance. `amount_type` is `google_calendar_minimum` or `google_partner_nightly_total`. `source_artifact` identifies the saved input; each row includes the source URL, capture observation time and snapshot path. The CSV flattens those provenance fields. Raw headers, cookies, credentials and opaque RPC templates are not exported.

## Run or reparse

Offline reparse of the completed source (no network):

```powershell
.venv\Scripts\python.exe -m compset.hotel_aketa --source data/hotels/aketa/google-form-canary-complete-2026-09-28.json --start-date 2026-09-28
```

A new bounded calendar capture, with the current date in `Asia/Kolkata`:

```powershell
.venv\Scripts\python.exe -m compset.hotel_aketa --live --start-date YYYY-MM-DD
```

The packaged `--live` collector opens the known Google Hotels entity once in ordinary Chrome/Scrapling, uses four uniquely observed controls to change two travelers to one adult and open Check-in, then reads the displayed calendar. It preserves the current one-night caption and selected-date supplier offers. It performs no direct endpoint replay and does not open supplier booking links. It stops on changed/ambiguous controls, a different hotel/currency, source challenges, 401/403/429 or browser failure. No proxy or identity switching follows a source failure.

The real research canary executed these same four form actions, followed by choosing 28–29 September and pressing Done. The first packaged-function attempt failed before network access because Windows lacked the IANA timezone database. Default date calculation now uses the standard-library UTC+05:30 offset for present/future India dates; the named `Asia/Kolkata` source context remains unchanged. Boundary and missing-database regression tests pass.

Root then personally executed the final `capture_google()` and `export_capture()` functions with an isolated output directory. This live check returned HTTP200, all four expected control actions, 30 indicative calendar dates, five abbreviated prices and no stop reason. It also returned five partner observations for the source-selected 2–3 October stay; those are separate from the dashboard's seven 28–29 September observations. Evidence is `data/hotels/aketa/verification-20260928T051555Z/google-calendar-20260928T051618335748Z.json` and its derived exports. The dashboard artifacts were not overwritten. The CLI wrapper delegates to these functions; the isolated proof invoked the functions directly to supply a separate output directory.

The live collector does not currently paginate to later months if Google omits a requested window; missing dates remain unknown. Direct JSON/RPC replay is not implemented for Google because an authenticated or opaque request schema was not needed to obtain this one-page calendar.

Validation executed:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_hotel_aketa.py -v
```

All 15 passed. Tests include wrong hotel/currency/party, missing one-night/year evidence, unavailable-versus-unknown, room-count provenance, K precision, party proof ordering, two-guest room rejection, unknown-provider isolation, negative breakfast labels, conflicting calendar values, strict scalar types, exports and the UTC boundary of Indian midnight without an IANA timezone database. Independent review follows separately under root coordination.

## Identity

The supplied [Google share link](https://share.google/i18UCuyHtGlcg4rB9) resolved to Hotel Aketa with Google knowledge entity `/g/12cnx4r7r`. The live [Google Hotels entity](https://www.google.com/travel/hotels/entity/ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ) confirms **Hotel Aketa**, **113/1-2 Rajpur Road, Hathibarkala Salwala, Dehradun, Uttarakhand 248001, India**. Hotel-local time zone is `Asia/Kolkata`. The website is [hotelaketadehradun.com](https://hotelaketadehradun.com/). No contact details or guest reviews are needed by the dataset.

## Historical source attempts and limits

These attempts preceded the successful Google Hotels canary; their amounts are excluded from the requested dataset.

| Source | Historical observation |
| --- | --- |
| MakeMyTrip | The SEO page opened HTTP 200 in ordinary Chrome, with default November dates and two-adult display prices. Changing the visible calendar to 28–29 September and adults from two to one, then APPLY, triggered the actual read-only hotel search. The returned body was only `200-OK`, with no rooms, rates or availability. It was recorded as unusable/unknown and not retried or replayed. |
| Google Hotels | A generic web reader showed an unsupported-browser response, but ordinary Chrome subsequently loaded the actual hotel page and yielded the successful requested-party calendar/canary above. |
| Booking.com / Agoda | Web-reader source pages identified the property or gave a shell. No direct requested-context rate request was made; Google partner displays supplied their public prices instead. |
| Expedia | Indexed property92850456 was identified; web-reader open failed. No direct rate collection occurred. |
| Official website | A direct public read returned HTTP406 Mod_Security. That source path was stopped without changing headers, proxies or identities. |

The actual MMT form submission established Aketa's MMT `hotelId=202108231240265962` beside its name. Its public requested context was `checkin=09282026`, `checkout=09292026`, `roomStayQualifier=1e0e`, `rsc=1e1e0e`, `_uCurrency=INR`, city/locus `CTDED`, country `IN`. These are observed request fields, **not returned quote evidence**. The request redirected from `/hotels/hotel-details` to `/hotels/hotel-details/`. A separate observed MMT `search-hotels/DESKTOP/2` response contained recommended properties; it was not attributed to Aketa. Saved attempt: `data/hotels/aketa/canary-2026-09-28-v2.json`.

No full rate batch against MMT, Booking.com, Expedia or Agoda occurred, and none is needed to describe the completed Google calendar scope honestly.
