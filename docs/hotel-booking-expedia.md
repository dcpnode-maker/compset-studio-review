# Hotel Aketa: Booking.com and Expedia evidence

The source adapters live in `compset/hotel_booking_expedia.py`. The callable contract is
`capture(source, hotel, context, output_dir=...)` followed by `parse(capture, hotel, context)`.
Each attempt writes an immutable sanitized evidence file and returns its SHA-256.
The portfolio orchestrator owns scheduling, cooldowns, source health and full date coverage.

## Current observed state, September 28, 2026

| Source | Identity and result | Price coverage |
|---|---|---|
| [Expedia](https://www.expedia.co.in/Dehradun-Hotels-Hotel-Aketa-Dehradun.h92850456.Hotel-Information) | Public property page confirms Hotel Aketa Rajpur Road Dehradun, ID 92850456, address 113/1-2 Rajpur Road. One browser session selected September 28–29; the Hotel-Search navigation returned HTTP 429, followed by a HTTP 403 challenge check. | No verified exact-stay quote. |
| [Booking.com](https://www.booking.com/hotel/in/aketa.en-gb.html) | The candidate property URL returned a JavaScript/robot-verification challenge on the primary public web read. Its direct property identity remains unverified in the registry. | No verified exact-stay quote. |

The live Expedia page also displayed ₹12,625 / ₹14,897 including taxes and fees for **October 12–13**,
while its date form initially showed September 29–October 1 and two travellers.
Those distinct contexts are precisely why a generic page-wide price scraper would produce false results.
These teaser amounts were never accepted for the requested one-adult stay.

Sanitized live evidence is in the ignored data directory:

- `data/hotels/aketa/direct-ota-evidence/booking-latest-capture.json`
- `data/hotels/aketa/direct-ota-evidence/expedia-latest-capture.json`

Booking used zero local browser navigations and one public web research read. Expedia used two observed
document navigations inside one local Scrapling/Playwright session and zero direct endpoint replays.
Neither source was retried after its challenge.

## Support boundary and repair

The adapters currently provide bounded public capture, verified property identity where returned,
immutable evidence and source health. **Exact-stay form automation and a usable price response contract
are not yet discovered for either source.** The parser therefore returns no rates, even for an HTTP 200
page or caller-supplied quote object. A future allowed successful capture will remain explicit unknown
until its returned property, dates, adult/child count, room count, currency and price basis are verified.
Do not mark these adapters as complete direct-price collectors.

Fresh capture uses an ordinary Scrapling DynamicSession, one fetch attempt and a 30-second navigation
timeout. It does not replay opaque GraphQL requests, change proxies, solve challenges, sign in, or book.
401/403/429 or visible challenges stop that source. Only canonical source property URLs qualify.
Browser navigation counts are observed, not inferred from a success flag. Cookies, headers, application
state and hidden form inputs are omitted. Challenge fingerprints are replaced with a generic marker.

To repair a source, obtain one normal public exact-stay response, preserve its sanitized fixture,
implement source-specific context extraction, then add tests for conflicting dates, guests, room count,
currency and stale/default teaser prices before enabling a direct-rate row. No access failure is
converted to unavailable, sold out, zero, or a synthetic price.

Verification: `python -m unittest discover -s tests -p test_hotel_booking_expedia.py`.
