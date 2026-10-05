# Order 001: standalone Airbnb observation pipeline

Authorized by the founder on 2026-09-28: standalone local Python tool using Scrapling, test any live BnBME Holiday Homes listing in Act One/Act Two, Dubai.

Scope: files in this standalone CompSetStudio directory only. Build Scrapling browser response capture and direct HTTP replay, listing/calendar/stay-quote parsing, provenance, local SQLite history, CSV/JSON export, bounded run command, tests and documentation. Dependencies installed only into .venv. No Yellow edits, runtime, migrations or database connections. No cloud services or paid APIs. No autonomous recurring job or broad crawl.

First test defaults: listing 1452665697263519565, AED, 2 adults, 0 children/infants/pets, en locale, three nights from property-local today +14 days, 90 calendar days. Defaults may be overridden from CLI.

Unavailable is not booked. A failed or unrecognized response remains unknown. Calendar nightly prices are distinct from complete stay quotes and averages. Record source evidence and exact requested context. Persist only public listing responses; request session secrets remain in memory. Stop bounded collection on access/rate limits and report failure honestly.

Acceptance: meaningful offline parsing/storage/error tests, an actual Scrapling live collection attempt with explicit coverage and limitations, independent review of delivered code and proof. No claim that missing nightly prices were collected. No claim that the attached prototype was already verified.
