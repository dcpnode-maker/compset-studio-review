# Order 002: local browser dashboard and model work allocation

Founder requested a proper architecture, parallel work across models and speed on 2026-09-28 after selecting the standalone local-browser approach.

Scope: CompSetStudio only, extending Order 001 with ARCHITECTURE.md, local HTTP server, static dashboard, launchers, UI and server tests, README and review evidence. Read-only collection of public listing/calendar/pricing data. Single collector job at a time. Bind 127.0.0.1 only; validate request origin, host and a custom request header. No external deployment or paid service.

Assignments: primary agent owns architecture/storage/CLI/server/integration; collection agent owns collect.py and its tests; normalization agent owns normalize.py and its tests; GPT-6 Sol high owns static dashboard; GPT-6 Luna will run bounded independent tests after an implementation slot frees. A nonimplementing agent reviews the integrated pipeline and personally executes proofs before a completion claim.

UI must show unknown/missing data, observation time and collection coverage. Never present fixture values as live data. Unavailable means unavailable, not booked. Freshness is measured per date, not inferred from scheduler frequency.
