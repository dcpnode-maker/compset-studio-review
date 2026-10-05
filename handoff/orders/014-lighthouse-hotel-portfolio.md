# Order 014: import the configured Lighthouse hotel portfolio

The user explicitly requests all hotels configured in their authenticated Lighthouse account in the local CompSet Studio system for comparison testing. This extends Orders012/013, preserving their ongoing implementation.

Root reads the visible account hotel list, profile/settings views and configured competitor membership using the authorized browser session. Record observed hotel names, provider IDs, public profile fields, source page, observation time, role and collection completeness. Account credentials, cookies, tokens and unrelated personal settings are excluded. Do not alter Lighthouse settings, prices, membership, subscriptions or trigger paid refreshes. Imported Lighthouse observations stay identified as Lighthouse data, not independently collected OTA results.

workspace_ui, after freezing its Aketa implementation, owns new compset/hotel_portfolio.py, tests/test_hotel_portfolio.py and docs/hotel-portfolio-import.md. Root supplies actual observed input under ignored data/hotel-portfolio/imports/. The importer validates and atomically stores namespaced profiles and configured relations, deduplicating only exact IDs. No guessed OTA identity merge. Root owns server route integration; workspace_data may expose the sanitized portfolio in intelligence.py, and ota_review may extend dual-workspace.js/.css with a hotel selector and truthful rate-coverage states.

Data and exports stay under ignored data/hotel-portfolio/. No account details in Git fixtures. Tests use synthetic fixtures. Every imported hotel must be selectable with its profile and source evidence. Only actually supported collections expose fresh rate actions. Unconfigured or uncollected prices remain unknown; the existing Aketa dataset is retained.

The visible account comparison table exposes competitor names without reliable competitor provider IDs. Root may add compset/hotel_memberships.py and tests/test_hotel_memberships.py to validate this separate label-only observation and expose it through intelligence.py. The UI must label these as configured names with unresolved OTA identity, never invent competitor IDs or prices. This adds read-only evidence, not collection or an account change.

No rotating proxies have been enabled. Preserve current source cooldowns and access stops, bounded requests, cache reuse and resumable jobs. Do not route around previous tool-execution denials or source access denials. Existing local activation and visual-QA limitations remain separately reported.

Acceptance: reconcile the visible account count with imported subject IDs, retain distinct competitor relations when observable, run importer and projection/UI contract tests, independently review the changes, and report any remaining account-list or rate-coverage gaps explicitly.
