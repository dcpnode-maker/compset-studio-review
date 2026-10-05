# Hotel Aketa: MakeMyTrip and Agoda adapters

Orders 008 and 009; standalone CompSet Studio. The implementation is in
`compset/hotel_mmt_agoda.py`. It exposes `capture(source, hotel, context,
output_dir=...)` and `parse(evidence, hotel, context)` for the common portfolio
orchestrator. Every call concerns one exact check-in/check-out pair. Nothing
inside the adapter loops across the 30-date job window.

## Verified direct-source result

On 28 September 2026, ordinary Chrome through Scrapling/Playwright loaded
[Aketa on Agoda](https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html), selected
28–29 September, one adult and one room, and submitted the public Search form.
The actual `/api/v1/property/room-grid` POST returned HTTP 200 with property
`110205`, its name, and `Sep 28 - Sep 29, 1 guest`. The paired request contains
`checkIn=2026-09-28`, `checkOut=2026-09-29`, `adults=1`, `rooms=1`,
`childrenAges=[]`, and `durationType=nightly`. The current form independently
echoes the dates and party and displays Indian rupees. Property identity was
also established from the public `propertyDetailsSearch` response beside the
name, Dehradun address and postal code 248001.

The returned room grid contains 24 offers. Fourteen explicitly show **one
adult, one room**, over five room types; ten two-adult alternatives remain in
source evidence but are excluded from the one-adult normalized dataset.
For example, Premium Single Room displays **INR 5,182 per night before taxes**,
including breakfast, a member-only condition and an automatically applied
coupon. Breakfast-plus-lunch, payment and cancellation variants are separate
products. A repeated provider `typeId` is not a unique rate-plan identifier:
the adapter retains a separate hash of public product terms for deduplication.

These are **direct Agoda price displays**, classified `indicative` with
`amount_type=ota_display_price`, `source_amount_basis=nightly_room_rate` and
`precision=displayed_integer`. The JSON numeric amount must agree with the
display amount; this does not prove an exact checkout amount. Tax inclusion is
explicitly false. For `Per night before taxes`, fee inclusion is unknown;
for the separately observed `Per night before taxes & fees`, fee inclusion is
explicitly false. Tax and fee amounts remain unknown for both labels. Conditions,
meals, cancellation, payment terms, source paths and actual stay context are
retained. No purchase, booking or login occurred.

Saved live research: `data/hotels/aketa/agoda-dated-one-adult-canary.json`.
Minimal public projection:
`data/hotels/aketa/agoda-verified/agoda-20260928T054705192569Z.json`.
The packaged capture function itself was executed once and saved:
`data/hotels/aketa/agoda-packaged-proof/agoda-20260928T054814068388Z.json`.
Its current parser produces **14 indicative rates across five room types**.
The packaged response omitted optional `isFit` and added a child promotion to
some offers. These actual variants were handled by offline reparse and
regression tests, without another network request. A child promotion never
changes requested zero children; the explicit adult/room offer, empty child
ages in the real request and returned one-guest summary must still agree.

The profile audit's single fresh canonical capture, observed at
`2026-09-28T06:55:45.690963+00:00`, introduced the explicit label
`Per night before taxes & fees`. Saved evidence:
`data/hotels/aketa/profile-audit/agoda-20260928T065647650951Z.json`.
Offline reparse accepts 14 one-adult indicative rates; the lowest is
**INR 5,169 per night before taxes and fees**, Premium Single Room with breakfast,
member-only and automatically applied coupon conditions, and pay-now and
cancellation terms. Only these two observed single-item label arrays are
accepted. Unrecognized, conflicting, missing or malformed price labels remain
unknown, and all property, stay, occupancy, currency and numeric checks still
apply. The repair and its verification make no additional network requests.

## MakeMyTrip diagnostic

[Aketa on MakeMyTrip](https://www.makemytrip.com/hotels/hotel_aketa_rajpur_road_dehradun-details-dehradun.html)
has verified provider ID `202108231240265962`. The previous real dated form
request returned HTTP 200 but its entire visible body was `200-OK`. It supplied
no usable rate or availability evidence. The adapter therefore reprojects that
saved diagnostic with **zero browser navigations and zero direct requests**.
It does not repeat the known unusable request across the date window.

Source: `data/hotels/aketa/canary-2026-09-28-v2.json`.
New minimal diagnostic:
`data/hotels/aketa/mmt-diagnostic/makemytrip-20260928T055155245520Z.json`.
It retains the original observation timestamp and actual request context,
alongside the current requested context. It yields `unknown` /
`source_contract_unavailable`; recommendations and default two-adult November
prices are excluded. Missing or changed saved diagnostics remain unknown and
never cause an automatic live retry.

## Capture and change handling

The Agoda capture opens one ordinary browser session and uses only uniquely
observed date, guest and Search controls. It derives date labels from the
requested stay and checks all actual returned request fields. The endpoint is
observed passively; there is no direct RPC replay, hash guessing, session export
or proxy switching. Request headers, cookies, tokens, GraphQL documents and
booking links are not persisted. The public response projection lists allowed
room/price/occupancy/condition fields explicitly.

After Search, a bounded 30-second readiness wait requires both the current
rendered hotel/currency/date/party controls and the exact stay's completed
room-grid response. It services browser callbacks in short slices and ends
immediately on a source stop or visible challenge. This fixes a next-date
canary where an eight-second sleep captured the empty page during navigation.
Earlier form controls are never copied into the final snapshot. A timeout
remains unknown with `submitted_result_timeout` and does not send another
search. The correction is covered by mocked navigation/response timing tests.
Root's fresh 29–30 September capture then passed the readiness conditions and
returned an explicit source negative for that exact stay. Evidence is
`data/hotel-pipelines/readiness-proof/latest-capture.json`.

HTTP 401/403/429 and challenge text stop capture. Changed or ambiguous form
controls, missing room grids, malformed schemas, contradictory source
availability, mismatched property/party/dates/currency and conflicting duplicate
prices yield unknowns. An initial default two-adult response can precede a
verified one-adult response; only the latter is eligible. Empty offers and
placeholder zero prices alone never become unavailable dates. Missing optional
presentation flags do not override explicit verified context.

A typed negative is accepted only after the property, exact requested dates,
room/adult/child counts and currency are verified from the current form and
paired request/response, and the response explicitly has boolean
`isSoldOut=true` and an empty `rooms` array. This produces observation
`status=unavailable`, `unavailability_verified=true` and reason
`source_unavailable_for_requested_stay`, with no rate rows. It describes the
requested stay on Agoda, not all hotel inventory or evidence of a booking.
Missing room schema, a string/number flag, mismatched context, or conflicting
positive rooms/responses remains unknown. A missing `rooms` field is never
normalized into an empty inventory array.

The existing common planner owns pacing, date coverage, cache/resume and source
stop behavior. This adapter does not schedule work or claim complete 30-date
direct coverage. Current direct-source proof covers 28–29 September price
displays and a verified 29–30 September source negative.

## Validation

Executed locally:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_hotel_mmt_agoda.py -v
```

**31 tests passed.** They cover real-schema price precision and conditions,
mixed default/final requests, exact typed party context, wrong property/dates,
missing currency/form evidence, two-adult offer exclusion, child promotions,
optional presentation flags, contradictory availability, duplicate variants,
numeric disagreements, source failures, secret projection, malformed nested
fields, delayed document/response readiness, bounded waiting, mid-wait stops,
final-snapshot isolation, typed stay-specific negatives, contradictory availability,
missing room schemas and zero-network MakeMyTrip diagnostics. Root coordinates independent
review and integrated persistence/coverage checks. Order 009 adds the observed
tax-and-fee exclusion label, unknown/ambiguous label rejection, and unchanged
context and numeric validation for that label.
