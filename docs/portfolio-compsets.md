# Portfolio comparison evidence

`python -m compset.portfolio_compsets` builds comparison records from saved data only. Optional repeatable `--pool path/to/snapshot.json` adds observed regional pools. `--data-root`, `--output`, and `--stale-hours` control local paths and the explicit age threshold. No requests, browser sessions, database writes, price refreshes or source-file changes occur.

The input portfolio is `data/portfolio-latest.json`. The default candidate sources are `compset-latest.json`, observed `airbnb_listings` membership in the portfolio, and matching local listing-cache responses. Additional pools accept `source_namespace: "airbnb"`, `candidates`, `observed_at`, `discovery_context`, and `coverage`. Existing discovery snapshots with `candidate_discovery_context`, `context`, or `report` also work. Each candidate requires an explicit numeric Airbnb listing ID; rejected rows and reasons remain in the pool audit.

Identities use `bnbme_direct:<property_id>` and `airbnb:<listing_id>`. The builder creates separate records for every official subject and every observed host listing. Titles, coordinates and operator names never establish an identity link. A direct-site candidate can unknowingly be the same physical unit; the record explicitly warns about this unresolved channel identity.

The existing adaptive comparison engine supplies the ranking policy: exact bedrooms, matching privacy type, nearby coordinates, bathroom and guest-capacity compatibility, then major guest amenities; review evidence is secondary. Size, building, property type and verified quality are soft comparisons when known. Unknown core fields produce provisional rows and stop automatic relaxation. Only ten or fewer eligible peers permit documented secondary-filter relaxation or radius expansion. Expansion uses retained candidates, never claims a new live geographic search, and remains capped at ten kilometres. Every candidate and each stage's reasons are retained.

`provisional_physical_match` means known coordinates, bedrooms, bathrooms and capacity passed the current physical gates while another required field is unknown. It is not a selected or verified competitor. An explicit saved privacy assertion can resolve room type only with a matched quote, source path and source time. Generic apartment titles, `room_types_name`, luxury wording and property codes do not establish privacy type, building name or a verified grade.

Local-cache enrichment verifies the exact public Airbnb `/rooms/<id>` URL and any explicit request ID before parsing. Unknown newer values do not erase older known evidence. Field-level source times control selection; conflicting observations remain visible. Source timestamps are never replaced by the comparison build time. Currency on an official property is its explicit official currency; Airbnb currency from a saved request is labeled `observed_request_currency`, not assumed to be a native property currency. No comparisons or exchange conversions depend on it.

Large operators require observed distinct listings sharing an explicit public host ID or a disclosed listing count. A marketing brand or a similar host name is insufficient. Corporate completeness remains unverified.

Outputs:

- `data/portfolio-compsets/latest.json`: compact subject index, build identity, aggregate coverage and relative artifact paths.
- `builds/<build_id>/candidate-pool.json`: deduplicated profiles, all normalized source observations, field conflicts and original discovery context/coverage.
- `builds/<build_id>/subjects/<namespace>-<id>.json`: subject evidence, source freshness, active criteria, stage history, every candidate decision, selected IDs and provisional physical IDs.
- `builds/<build_id>/index.json`: immutable index for that evaluation; `subjects.csv` is the current local export.

New builds preserve all older build folders. The latest index is atomically replaced only after all comparison files are written. Repeated evaluations have separate build identities because staleness is evaluated at a specific time. A saved index is a sample-coverage report, not proof of current availability or exhaustive market inventory. Price, booked occupancy and hotel-star metrics are deliberately absent.

Initial local result: 113 official subjects and 60 observed Airbnb subjects, 374 unique candidates, 1,124 profile observations. There are 112 official subjects with unknown privacy type and nine Airbnb subjects with unknown bedroom count. Saved candidates cover Dubai only; Riyadh and London remain explicit geographic gaps until regional snapshots are acquired.
