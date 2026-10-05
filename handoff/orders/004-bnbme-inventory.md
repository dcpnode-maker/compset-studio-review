# Order 004: BnBMe inventory before competitor collection

Founder direction, 2026-09-28: first build a database of BnBMe's active properties across Dubai, Saudi Arabia and London, with all publicly available property attributes, public business host details and contextual price observations. Defer new competitor scraping until this inventory is reviewed; subsequent competitor collection should be slow and bounded.

Scope: standalone CompSetStudio only. Add official-site catalogue capture, public Airbnb portfolio observation, evidence-based cross-channel identity links, SQLite inventory snapshots, detailed JSON/CSV exports, portfolio dashboard, tests and independent review. Preserve existing observations. No Yellow edits.

Retain all returned public listing attributes, including photos/floor-plan URLs, description, amenities, room counts, location, pricing fields and their context. A published listing is not automatically proven bookable. Mark bookability only from an explicit dated availability/quote response. Unknowns remain explicit; catalogue count without pagination/count metadata does not prove complete corporate inventory. Public platform host IDs are separate from business operator identity; review count is never portfolio size. Name/title/location similarity is not a verified cross-channel link.

Use AED, SAR and GBP as returned; never compare unconverted currencies as equal. Exact and rounded amounts remain separate. Undated advertised prices are not dated stay quotes. Record source, source path, timestamp, dates, guests, currency, rate option and price basis for each observation when available.

Slow collection: one detail/price request at a time, at least one second between starts, cache and checkpoints, finite budget, no retries after 401/403/429. Discover request contracts from the actual public site; do not invent pagination or endpoints. No bookings or messages.

Preserved next-stage comparison policy: build a canonical attribute profile before comparison; prioritize bedrooms, bathrooms, usable space, location, accommodation/building type and major amenities. Reviews and minor amenities rank rather than exclude by default. At 10 or fewer eligible listings, secondary rules may relax and the radius may expand within an explicit maximum, with an audit log; never hide a rule/radius change or invent a quality grade. Implementation of that workflow follows the inventory priority.

Ownership: discovery agent owns portfolio.py and profile/catalogue probes; dashboard agent owns static assets and operator research; parent owns inventory.py, CLI/API, storage, integration and docs. Independent reviewer executes its own proof.

28 September follow-up: research actual Airbnb unavailable-calendar behavior to prevent wasted retries. Scope includes the official Help research note, public guest-picker proof, a conservative typed-calendar preflight for the existing competitor batch, and regression tests. New competitor collection remains deferred. A failed exact stay is not evidence that every night is booked; checkout-only dates are preserved. The preflight may skip a quote only on positive evidence of a violated rule or blocked sleeping night, never on missing data or CSS styling.
