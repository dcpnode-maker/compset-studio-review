# Observed Google Hotels calendar request

The custom collector in `compset/google_calendar_network.py` opens Hotel Aketa's
known public Google Hotels page, selects one adult, and opens its calendar. It
observes the page's actual RPC responses and identifies the calendar by its dated
price records and comparison with every displayed price. It then replays that
exact request once inside the same browser session. RPC identifiers, session
parameters and the request body are discovered; the failed Gemini `H9aBbd`
assumption is not used.

The successful observed request used `POST` to
`https://www.google.com/_/TravelFrontendUi/data/batchexecute` with RPC identifier
`yY52ce`. This is an internal page endpoint observed in the tested session, not a
documented public Google rate API. The collector discovers the identifier and
request body again from the browser; it does not assume this identifier or its
parameters will stay valid. The sanitized evidence is in `discovery.json`,
observation index 5 in the final proof run.

Run from `E:\YellowWorkspace\CompSetStudio` with a **new** output directory:

```powershell
$env:TEMP = 'E:\YellowWorkspace\Temp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = 'E:\YellowWorkspace\Caches\python-bytecode'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m compset.google_calendar_network --output data/probes/google-calendar-new
```

Requires the existing Scrapling/Playwright environment and installed Chrome at
`C:\Program Files\Google\Chrome\Application\chrome.exe`. There are no paid API
calls or model calls. Temporary browser data is on E:. Cookies, full request
headers, session parameters and replay bodies remain in memory and are not
written to the result files. The browser closes when the finite run ends.

`api-calendar.json` contains the requested dates obtained from the replay, their
context and provenance. `replay.json` contains sanitized date/price fixtures;
`discovery.json` records RPC shapes and request counts. `latest.json`, `rates.csv`
and `calendar.csv` contain the independently parsed rendered calendar. A failed
optional replay preserves the rendered result. Missing data is unknown and does
not establish that a hotel is unavailable. Changed controls, challenges and
access limits stop collection; there is no proxy fallback or guessed-ID loop.

On 30 September 2026, the final live proof in
`data/probes/google-api-final-20260930` discovered `yY52ce`, observed the known
Aketa entity in its request and received HTTP 200 for the identical replay.
The response contained 32 dated records; all **30 requested dates (30 September
through 29 October)** were extracted and matched the rendered integer prices.
The browser also supplied one separate partner display row. There were zero
unknown or unavailable dates in this requested calendar window.

The measured replay took **0.187 seconds**; obtaining the initial browser calendar
took **23.850 seconds**, and the full run took **25.468 seconds**. The whole browser
session made 202 requests, including assets/telemetry, of which 52 were to
`www.google.com`; seven observed RPC responses included the single replay. This
does not establish that a full run costs one HTTP request.

Prices are indicative displayed calendar minimums. The response has both an
unrounded numeric value and a displayed integer; both are preserved without
claiming that either is a final payable total. Room count, taxes, fees, supplier,
room type and cancellation inclusions remain unverified. The proof covers Aketa,
INR, one adult and this session; it does not establish other hotels, multi-hotel
batching, a 365-day calendar, persistent tokens or long-term endpoint stability.

Nine focused network/parser tests verify JSON framing, the observed currency/
date/price structure, scalar/context rejection, conflict handling, string
redaction, exact exported-price comparison, the mandatory hotel identity gate,
request-index provenance after parse errors and saved access-limit diagnostics.
Rounding diagnostics never authorize a different exported amount. The separate Gemini comparison runner has five transport-boundary
tests and retains its real HTTP 400 / unmatched SSR evidence separately.

Run the 14 offline regression tests (no live requests):

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_google_calendar_network tests.test_gemini_google_probe -v
```
