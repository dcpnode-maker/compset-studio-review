# Airbnb calendar semantics and bounded retry recommendations

Researched 28 September 2026 using four focused searches and official Airbnb Help pages only. This lane read existing local subject captures; it did not operate a live Airbnb calendar, request a reservation, or change implementation files. The retry policy below is an engineering recommendation inferred from documented business rules, not an Airbnb API contract or published retry schedule.

## Evidence from official Help

| Source | Short source excerpt | What the source establishes |
| --- | --- | --- |
| [Updating your host calendar — 447](https://www.airbnb.com/help/article/447) | “blocked nights have a line through the date” | In the **host** calendar, white nights are available and struck dates are blocked. Selecting a blocked date can reveal its reason. This is not a documented universal color/glyph specification for the guest date picker. |
| [Why your calendar nights may be blocked — 3612](https://www.airbnb.com/help/article/3612) | “restricted check-in or checkout days” | Blocks can come from minimum nights, availability windows, preparation time, advance notice, arrival/departure restrictions, linked calendars, pending or confirmed reservations, cancellations, verification, missing information, or local stay-length restrictions. Blocked does not identify which cause applies. |
| [Set minimum and maximum nights — 880](https://www.airbnb.com/help/article/880) | “custom rules for each day of the week” | Trip length can have a minimum and maximum, with minimum-night rules customized by check-in day. The same night can participate in a valid longer stay while a shorter proposed trip fails. |
| [How rule-sets work — 2061](https://www.airbnb.com/help/article/2061) | “Choose the days that guests can check in and out.” | Arrival and departure permissions are distinct availability rules. Date-specific rule-sets can override existing pricing and availability settings. |
| [How far in advance you can book — 3593](https://www.airbnb.com/help/article/3593) | “Try adjusting your dates if you have flexibility” | Dates may be unavailable because the calendar is not open that far ahead, a booking exists, a minimum stay applies, or the home is unavailable. Alternatives include different dates or a split stay; no single cause can be inferred from unavailability alone. |
| [Search for Airbnb home listings — 252](https://www.airbnb.com/help/article/252) | “weekend stays, weekly stays, or monthly stays” | Flexible search supports these durations; specific-date search can allow a margin such as plus/minus three days. Search context includes adults, children, infants, and pets. Flexible results are alternative contexts, not quotes for the original exact stay. |
| [Check if a place is available for your dates — 137](https://www.airbnb.com/help/article/137) | “travel dates and number of guests and pets” | Availability search depends on both dates and party composition. Airbnb encourages checking calendar accuracy; a search appearance is not a reservation confirmation. |
| [If your reservation couldn't be completed — 3498](https://www.airbnb.com/help/article/3498) | “requirements, like minimum nights to book” | A generic reservation failure can involve identity verification, payment, stay requirements, or party-risk screening. The generic failure does not prove that calendar nights are blocked and must not be flattened into unavailability. |
| [Booking errors for a software-connected listing — 2934](https://www.airbnb.com/help/article/2934) | “those dates are now blocked” | A booking-time message that the calendar needs updating or dates are no longer available can reflect changed software-provider availability. That specific message is a business availability result, despite containing the word error. |
| [Customize booking settings — 484](https://www.airbnb.com/help/article/484) | “requirements that aren’t met” | Advance notice, preparation time and guest requirements can prevent search appearance. Lack of Instant Book does not by itself mean a stay cannot be requested. |
| [Update the Airbnb app — 2819](https://www.airbnb.com/help/article/2819) | “an outdated version might be causing problems” | Access problems can arise from software state. Airbnb suggests updating the app and using its website when app access fails. This page does not define calendar HTTP retries or guest-calendar loading semantics. |

Each quoted source excerpt above is under 25 words. All substantive calendar claims come from Airbnb's official pages. The four searches covered blocked/grey dates and trip length; flexible dates/guest count/booking errors; arrival/departure restrictions; and technical loading problems. No official guest-calendar grey-color legend or checkout-only visual specification was found in this bounded search.

## Distinguish nights, permitted actions, and whole trips

Store these separately when actually observed: nightly availability, check-in permission, checkout permission, minimum/maximum nights, and whole-stay eligibility for the exact party. Keep an unobserved rule null. A date disabled as a **check-in** need not be a blocked sleeping night, and a date selectable only as **checkout** does not prove that sleeping there that night is possible. This separation is inferred from Airbnb's distinct trip-length and arrival/departure rules. Exact guest-picker behavior must be verified using current accessible labels, messages, or typed response fields; do not infer it from grey styling alone.

For the project's exclusive checkout convention, a 12–15 October stay consumes nights 12, 13, and 14; 15 is the departure action. A whole-trip failure does not identify which night or restriction caused it. Do not mark every date in that range unavailable merely because the whole trip fails. Likewise, all displayed nights looking open does not prove a valid arrival, departure, length, party, or final booking.

Capacity and party restrictions are context-specific. Preserve the requested adults, children, infants, and pets. When an explicit current source says the party exceeds the permitted maximum, record a guest-constraint result, not a global calendar block. Changing guests, dates, or duration creates a different request; never silently make that change to manufacture an available quote. Identity, payment, or screening requirements also differ from nightly availability and do not authorize bypassing them.

## Recommended classification

“Terminal” here means **complete the current attempt without an immediate retry of the same context**. It does not mean permanently unavailable; a future deliberate refresh can observe changes.

| Observed signal | Result to store | Immediate same-context retry |
| --- | --- | --- |
| A successfully loaded, correctly matched listing/date/party response explicitly says the exact stay is unavailable, or a trusted typed whole-stay flag is false | `unavailable_for_context`; retain message and evidence | No. Complete/cache the business result. Do not call it booked. |
| Explicit minimum/maximum stay, disallowed check-in/checkout, notice/window rule, or guest-capacity rejection | `constraint_not_met`; retain observed reason | No. Offer a clearly labeled alternative only within authorized exploration. |
| A correctly loaded calendar explicitly reports a night unavailable | Night `unavailable`, cause unknown unless supplied | No immediate repeat for that observation. It does not by itself settle every possible stay. |
| “Calendar needs updating” / “dates no longer available” during a software-connected booking flow | Availability changed / unavailable for the attempted stay | No blind replay. The specific documented message is a business result, not just a transport error. |
| Generic “reservation couldn't be completed” without a specific cause | `unknown_booking_failure`, with message | Do not mark unavailable. Inspect already available evidence once; stop for account/payment/screening action rather than repeatedly retrying. |
| Spinner, skeleton, blank month, detached UI, timeout, missing response body, or truncated data | `unknown_transport_or_loading` | One bounded recovery/read after backoff if allowed; never interpret emptiness as all unavailable or all available. |
| HTTP success but unfamiliar/missing calendar structure, only HTML shell, absent quote nodes, or conflicting context | `unknown_schema_or_context` | Reuse saved payload for parser diagnosis first. At most one controlled fresh recovery if transient loading is plausible; repeating identical schema failures wastes requests. |
| HTTP 429, transient server error, or connection failure | `unknown_transport` with status | Bounded retry with backoff; honor server retry guidance. A repeated failure ends as unknown and preserves progress. |
| Authentication requirement, challenge, authorization denial, or removed listing | Access-required/denied/removed as observed | Stop this attempt. Do not bypass access controls or infer booking occupancy. |
| Price returned with no explicit stay-eligibility confirmation | `price_observed`, eligibility unknown | Preserve the price and context. Do not infer bookability solely from a positive price. |

No official Help page found here specifies retry counts or delays. A practical project default is one initial attempt plus at most one automatic recovery for a genuinely transient read, then stop unknown; a schema mismatch should be solved from the saved response rather than refreshed repeatedly. Keep retries within the existing global pacing/budget and cooperative pause policy. This proposed count is intentionally a project choice.

## Cache and alternative-date recommendations

Use a context key including listing ID, check-in, exclusive checkout, adults/children/infants/pets, currency, locale, and the observed source version where relevant. Save business negatives as usable observations with `observed_at`, source URL/path, context, reason, and `retryable=false` for the current attempt. They are completed research results, not failed jobs to resume immediately. Missing daily observations remain unknown even when an exact-stay business result is known.

Transport/schema failures get a distinct reason, retry count, next permitted attempt, and saved evidence. Resume from completed context keys and do not rerun them merely because another property failed. A parser repair can reprocess the same stored payload without a network call. Keep any previously successful observation alongside later failures, with separate timestamps.

If alternative dates are authorized, prefer one constrained exploration of known compatible dates, preserving length and party where possible. Label each quote with its actual dates. Airbnb's Flexible tab and plus/minus search are options, not proof that an alternative automatically works. Do not contact hosts or create bookings for this research workflow.

## Existing subject evidence, not a new live UI check

Subject listing: `1567889913136387224`; AED; 2 adults; no children, infants, or pets.

- Saved run `b38c5c45d3ef20664c4c5dee`, observed `2026-09-27T23:17:17.132619+00:00`, requested **12–15 October 2026**. Its `source.json` contains `BookItAvailability.isAvailable=false` and `unavailabilityMessage="Those dates are not available"` at `$.payloads[2].body.data.node.pdpPresentation.bookIt.availability` (also present in payload 5). This is an explicit exact-stay business negative; stop immediate identical retries. It does not disclose why and does not establish booked nights.
- Saved run `85a07d40e892c7c48e129657`, observed `2026-09-27T23:18:17.891052+00:00`, requested **17–20 October 2026**. The parent workflow previously observed this context available. This lane verified saved exact price evidence of **AED 2,244.85 total**, plus a rounded **AED 2,245 for 3 nights** display. The raw `productItemDetail.guestOptions[0].priceString` is at `$.payloads[2].body.data.node.pdpPresentation.bookIt.productItemDetail.guestOptions[0].priceString`. This is a different stay, not a retry of 12–15 October and not a new booking confirmation.
- At this lane's file read, `data/latest.json` still had `not_observed` daily placeholders and a `no_price` parsed row despite the price strings in the saved source. That is a parser/encoding coverage problem. It should be diagnosed from the saved UTF-8 payload, not treated as no availability and not repeatedly refetched. Files may be refreshed by the parent after this observation.

The unavailable and alternative available contexts can coexist. They do not justify extrapolating a full calendar or a reason for blocked dates. Root's separate live calendar proof should document current labels/roles and selection behavior for grey, struck, check-in-restricted, and checkout-only dates before adding UI-specific assumptions.

## Live guest calendar verification by the parent

On 28 September 2026 the public Act One / Act Two listing was opened with 12–15 October 2026, two adults and AED. The loaded booking panel showed the unavailable-stay message and a Change dates button. No reservation action was taken.

The unselected October picker showed unavailable days grey and struck through, with disabled buttons and unavailable accessible labels. However, dates already selected through the URL had dark selection circles despite being disabled. Color alone is therefore insufficient.

The live calendar distinguished these three cases:

- 17–19 October: eligible arrival dates with a two-night minimum.
- 20 October: an available sleeping night, but an arrival cannot satisfy the two-night minimum before the next blocked night.
- 21 October: checkout-only, despite the saved typed calendar reporting its overnight availability false.

After selecting 19 October as arrival, 20 October became disabled as a too-early checkout. Later dates, including previously open November dates, also became disabled because the proposed continuous stay would cross blocked nights. These picker labels are selection-dependent and must not overwrite the underlying nightly calendar.

Selecting 21 October as checkout produced a two-night quote for 19–21 October: selected non-refundable total AED 1,607.29, refundable alternative AED 1,758.10, with a rounded headline AED 1,608. The visible Reserve button was not clicked. This confirms that an unavailable overnight date can be a valid departure boundary; a positive quote is not a completed reservation.

Screenshots: `screenshots/airbnb-unavailable-calendar.png` and `screenshots/airbnb-checkout-only-stay.png`. Browser proof is an observed UI snapshot, not an undocumented API guarantee.

The two earlier saved source files were also reparsed with the current adapter without any network requests. Run `7c8472251ed2e9ece7d926b7` now has 90 observed days (66 available, 24 unavailable, no numeric nightly prices) and the explicit 12–15 October stay rejection. Run `983738652363c27f865eb351` has the two exact 17–20 October rate-option totals; its own capture lacks daily calendar data, so those dates remain unknown in that run. The earlier parser gaps are preserved in historical artifacts, not retried as failed availability.
