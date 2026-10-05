# Calendar semantics and quote preflight review

Date: 28 September 2026. Implementation: `/root/scrapling_research`. Independent reviewer: `/root`, who did not implement availability.py or the batch changes.

Reviewed the typed calendar preflight, batch request ordering, checkpoint completion and twelve new regression tests. Sleeping nights exclude checkout; arrival/departure flags and minimum/maximum nights remain separate. Missing, conflicting, failed or unverified calendar responses cannot suppress quotes. No fabricated prices or booked-status inference were found. A proven business negative is a completed observation for the current context, subject to the existing one-hour monitoring freshness limit.

Reviewer personally executed `python -m unittest tests.test_availability -v`: twelve passed. Tests prove one HTTP request instead of two on a verified negative, two requests on an unknown response, and zero new browser/HTTP calls when the completed negative is resumed. No live competitor collection was run.

Additional reviewer proof used the saved BnBMe calendar response bodies. Original legacy envelopes lack captured request context and correctly decline the optimization. A separately constructed test fixture with explicit synthetic request metadata rejects 12–15 October, allows the quote for 19–21 October despite checkout-night availability false, and rejects arrival on 20 October. Original source observations were not changed. Details are in local `data/calendar-preflight-proof.json`.

The parent also directly inspected the live public guest date picker: grey/struck dates, selection-dependent disabled dates, the two-night minimum, checkout-only 21 October, and a displayed quote for 19–21 October. Screenshots and official Airbnb sources are in `docs/airbnb-calendar-semantics-research.md`.

Accepted within this scope. This is a conservative request-saving rule, not an undocumented Airbnb API guarantee or automatic semantic repair. A later deliberate refresh can observe changed availability. No reservation or host message was sent.

Reviewed SHA256: availability.py `0070f0bf2c3a4221eeda062fbf9cc0a9754d9acd556f4fee9cb706108a4cb8d8`; batch.py `26d6d26d39075bcdbb96029136a5d2ef17ee23970d77e6b4d3c796b68b2dae59`. The independent runtime reviewer separately reran the full integration suite after making its filesystem-revision test deterministic: 153 passed. SQLite integrity check returned `ok`. A fresh-cache resume proof retained 113 official properties and 60 Airbnb listing records with HTTP methods replaced by failing stubs: zero HTTP requests, including cached negative/error results. Host pacing sleeps were disabled in that offline proof only.

Final integration note: restarting the idle local dashboard process was rejected by automatic approval review with “blocked by policy”; no more specific reason was provided. Saved code is validated, but the existing server process has not loaded its newest server-level changes. The preflight is loaded by new worker subprocesses.
