# One-adult price evidence and collection contract

Order 005 research, 28 September 2026. Read the order and attached handoff in full. This lane made no Airbnb requests; it inspected saved public response fixtures and the local collector. Two focused searches and official Scrapling documentation reads were used. Installed Scrapling version: `0.4.15`. Proxy configuration below is a recommended integration contract, not a claim that a route was validated.

## What the saved one-adult capture proves

Source: `data/runs/521a6b08734da5df84230398/source.json`, SHA256 `2ba4bbf0de49fcd313147d6cad1b2aaea6c2b2993dc92a138be6b51ea0437daf`. Requested calendar interval is `[2026-09-28, 2026-10-28)` in the parent-computed Dubai-day context: 30 dates, 8 typed available, 22 typed unavailable, 0 numeric nightly prices. The separate quoted stay is 17–20 October, one adult, zero children/infants/pets, AED. Do not present this three-night quote as prices for the 30 individual nights.

The body paths below are exact for this fixture; array positions are observations, not stable API contracts.

| Source path | Observed type/value | Correct interpretation |
| --- | --- | --- |
| `$.payloads[6].body.data.merlin.pdpAvailabilityCalendar.calendarMonths[*].days[*].price` | Object: `__typename="MerlinCalendarDayPrice"`, `localPriceFormatted=null` | A date-associated price container exists, but no amount was supplied. |
| `$.payloads[8].body.data.merlin.pdpAvailabilityCalendar.calendarMonths[*].days[*].price.localPriceFormatted` | Null on all 61 returned day objects | Replay also supplied no nightly prices. Payload 6 has 365 day objects; all 426 objects across both responses have null prices. These overlap and are not 426 distinct nights. |
| `$.payloads[4].body.data.node.pdpPresentation.bookIt.productItemDetail.guestOptions[0].priceString` | String, AED `2,264.65 total` | Exact source-formatted non-refundable stay total; selected option ID `51`. Payload 7 repeats it. |
| Same path, option `[1]` | String, AED `2,488.50 total` | Separate refundable stay total; option ID `3`, not selected. |
| `$.payloads[5].body.data.presentation.stayProductDetailPage.sections.sections[2].section.structuredDisplayPrice.primaryLine` | Object with price AED `2,265`, qualifier `for 3 nights`, style elsewhere `TOTAL_ONLY` | Rounded marketing display total; not the exact amount or an individual night's price. |
| Same section, `structuredDisplayPrice.explanationData.priceDetails[0].items[0]` | Description `3 nights x AED 754.88`; priceString AED `2,264.65` | Displayed average-like multiplier for that stay. No per-date allocation. Do not divide or spread it into calendar rows. |
| Same section, `productItemDetail.explanationData.priceDetails[1].items[0]` | Description `Price after discount`, priceString AED `2,264.65`, `originalPriceString=null` | Preserve the reported line. No numeric original price or discount amount is established. |
| `$.payloads[4].body.data.node.pdpPresentation.bookIt.productItemDetail.guestOptions[*]` | IDs, selected Boolean, title, priceString, cancellation subtitle; `kickerText`, `disclosureText`, `guestOptionLink` null | These are cancellation/rate options. The word `guestOptions` and IDs do not describe guest counts or per-adult surcharges. |

No `priceHeatmap` key or heatmap `__typename` was found anywhere in this capture's response bodies. This is **absent response data**, not a populated heatmap whose cells are null. The collector deliberately excludes `priceHeatmapDateRange` from stay-context extraction so it cannot overwrite the selected check-in/out dates. A request-side heatmap date-range option, if observed, is not proof of a returned nightly price array. No hidden numeric nightly field appeared alongside `price.localPriceFormatted`: the observed calendar day keys were type, date, availability, min/max nights, check-in/checkout permission, bookable and price.

The inspected discountCopy/discountData fields are null. The returned explanation groups do not itemize cleaning fees, service fees, taxes, extra-adult adjustments or a base daily rate. Those amounts and inclusion flags remain unknown. Preserve the explanation groups verbatim; do not infer a fee breakdown from the difference between refundable and non-refundable totals.

Older two-adult run `85a07d40e892c7c48e129657` contains AED 2,244.85 / 2,466.50 totals for 17–20 October, plus a `3 nights x AED 748.28` display. It is a different observation and cannot be relabeled one-adult. The price difference between runs does not establish a guest modifier: capture time and other pricing state also changed. Older blocked run `7c8472251ed2e9ece7d926b7` contains 487 returned calendar day objects across overlapping responses, again with all `localPriceFormatted` values null.

## Actual request context is the guest evidence

Payloads 4 and 7 are BookIt responses whose `request_context` explicitly includes listing ID `1567889913136387224`, check-in/out 17–20 October, adults `1`, children/infants/pets `0`, currency `AED`, locale `en-IN`. Their exact stay totals can be tagged guest-context verified. The requested run locale was `en`; retain the observed locale separately instead of silently replacing it or claiming the price is invalid merely because the language locale changed.

Calendar payloads 6 and 8 include listing ID, currency, locale and month/year/count, **without an adults/children/infants/pets parameter**. Their availability remains an observed listing-calendar fact. Even if a future calendar response contains an amount, it must remain guest-context unverified unless actual source request/response evidence establishes the party. Payload 5, the Sections response, has only currency/locale in captured request context. The normalizer's inherited run defaults are not proof that this individual response was priced for one adult. Prefer the verified BookIt option source; do not certify a Sections-only quote from inherited defaults. Initial page URL envelopes contain party parameters but lack a separately captured listing ID; do not manufacture provenance from parser defaults.

Recommended artifact fields:

- `requested_context`: listing, interval, one adult, zero other guests, currency, requested locale; keep this separate from each source's captured context.
- Per date: retain typed availability, arrival/departure rules, min/max nights, observed timestamp and source path. Scaffold missing dates as unknown.
- `calendar_display_amount`: positive decimal string parsed from the date's actual `price.localPriceFormatted`, or null. Preserve the original display and its display precision.
- `nightly_amount_for_requested_party`: populate only from a genuine date-specific source amount with explicit matching captured listing, one-adult party and currency. Otherwise null, with a reason such as `guest_context_unverified` or `nightly_price_not_returned`.
- Base amount, taxes, cleaning fee and guest modifiers: null until independently supported by explicit returned fields. No arithmetic allocation of totals.
- `stay_quotes`: preserve exact option totals, rate/cancellation option, actual dates, raw explanation groups, and `guest_context_verified` derived from matching BookIt envelope evidence. Rounded displays remain separate.
- Coverage must distinguish observed calendar days, numeric calendar-display days, verified one-adult nightly-price days, and exact contextual stay quotes. This canary's nightly counts are both zero even though its stay quote exists.

## Existing capture path and limits

`collect()` puts the requested party/dates/currency in the listing URL. `DynamicSession.fetch(..., page_setup=setup, page_action=action)` runs the setup callback before navigation. `setup` attaches a request listener that records observed allowlisted GET templates in memory and a response listener that notes stop statuses. `action` waits and, when needed, opens an observed date control; it does not reconstruct prices from disabled UI labels. `capture_xhr` captures matching API responses. The collector then processes `response.captured_xhr` through the read-operation allowlist, saving only status, sanitized origin/path, public body and extracted request context. `request_context()` reads actual URL variables; it does not infer absent guest parameters.

`replay_observed()` reuses observed headers/hash/variables through `FetcherSession.get`; calendar replay changes only already-observed month/year/count. `_payload()` parses `response.body`, strips sensitive JSON keys and retains public request-context fields. `normalize()` preserves source paths but currently merges captured context onto run defaults. The one-adult artifact layer therefore must examine the originating envelope rather than treating normalized `adults` as verified. `template_sink` is an in-memory handoff only; never persist request headers, opaque session parameters or proxy credentials.

An unknown API operation may be named in diagnostics but its body is not automatically admitted to the replay/normalization allowlist. No price-heatmap operation was observed in this canary's operation names. Missing data therefore does not justify inventing an endpoint, hash, parameter or historical API key.

## Documented Scrapling interfaces and sticky route recommendation

Scrapling documents `FetcherSession` reuse of cookies and its connection pool, `session.get(url, headers=..., params=...)`, static `proxy=...` or `proxies={"http": ..., "https": ...}`, and per-request proxy overrides. `proxy_rotator` cannot be combined with static proxy settings. HTTP timeout units are seconds; `verify=True` is the documented default. The `.body` response is suitable for JSON decoding. Pin one explicitly selected route to the entire HTTP session and keep certificate verification enabled. This policy is an integration recommendation rather than a Scrapling sticky-session parameter. [Official HTTP documentation](https://scrapling.readthedocs.io/en/latest/fetching/static.html)

`DynamicSession` accepts static `proxy` as a URL or server/username/password object. `page_setup` precedes navigation; `page_action` follows it. Session-level `capture_xhr` accepts a URL regex; each `response.captured_xhr` item exposes URL, status, headers and body. Browser timeout units are milliseconds. The documentation says browser proxy rotation creates separate temporary contexts, while regular sessions reuse their browser state. Use one static route per browser session for this workflow. [Official dynamic documentation](https://scrapling.readthedocs.io/en/latest/fetching/dynamic.html)

`ProxyRotator` supplies thread-safe cyclic or custom selection; it does not validate route honesty, guarantee a stable exit IP, or certify residential/mobile provenance. Do not equate a route configured once with an externally verified sticky exit: an upstream service could rotate internally. [Official ProxyRotator reference](https://scrapling.readthedocs.io/en/latest/api-reference/proxy-rotation.html)

Recommended integration: select direct access or one validated explicit route once; apply the same route to browser bootstrap and subsequent HTTP replay; record a credential-free route ID, source and validation time; retain actual observed request context. Keep the route for the whole listing/context batch. Browser and HTTP sessions are separate cookie stores, so route equality is not evidence that their session state is identical. Existing captured headers can bridge an observed read only as authorized, without logging secrets. Stop the target attempt on existing 401/403/429/challenge conditions; do not rotate after a denial. HTTP success at a neutral validation URL is not evidence that Airbnb permits or will serve that route. Route category remains unknown unless supported independently.

## Implemented pure artifact boundary

`compset.nightly_rows.build_nightly_rows(capture, result)` now implements the separation above without network or filesystem writes. It validates an exclusive 30-day, one-adult context, resolves normalized source paths back into the actual envelopes, and verifies requested party fields without inheriting defaults. Calendar source disagreements leave amounts unknown. Product-level explanation groups are attached only to the selected rate option they describe; they are not copied as a fee breakdown for other cancellation options.

Coverage keys are `requested_days`, `observed_calendar_days`, `available_days`, `unavailable_days`, `unknown_days`, `calendar_display_price_days`, `verified_nightly_price_days`, and `verified_one_adult_stay_quotes`. The saved canary was processed locally: 30 observed dates, 8 available/22 unavailable, zero calendar-display or verified-nightly price days, and two verified exact one-adult stay-option totals. Every nightly amount remained null. This proves the artifact semantics against the saved source, not future source coverage or booking availability.
