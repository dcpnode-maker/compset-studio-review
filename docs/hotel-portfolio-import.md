# Importing the configured Lighthouse hotel portfolio

Order 014 adds a local inventory importer. Root records visible hotel identities and configured competitor membership from the user's authenticated Lighthouse account; this module does not browse, log in, fetch rates, alter the account or trigger a paid refresh.

## Observation input

Save observations under the ignored `data/hotel-portfolio/imports/` directory. Example values below are synthetic:

```json
{
  "schema_version": "lighthouse-portfolio-observation.v1",
  "observed_at": "2026-09-28T12:00:00+00:00",
  "source_url": "https://app.mylighthouse.com/hotels",
  "coverage": {
    "account_subject_count": 1,
    "subject_list_complete": true,
    "competitor_membership_complete": false,
    "notes": ["Subject list observed; competitor membership only partly inspected."]
  },
  "hotels": [
    {
      "provider_id": "001",
      "title": "Example City Hotel",
      "role": "subject",
      "city": "Example City",
      "room_count": 40
    },
    {
      "provider_id": "900",
      "title": "Example Competitor",
      "role": "competitor"
    }
  ],
  "relations": [
    {"subject_provider_id": "001", "competitor_provider_id": "900"}
  ]
}
```

`provider_id` must be the exact observed string; integer coercion is rejected so leading zeroes and large IDs survive. `name` is accepted as an alternative to `title`. A hotel may use `roles: ["subject", "competitor"]` when both roles are observed. Optional public attributes are `city`, `country`, `address`, `latitude`, `longitude`, `room_count`, `star_classification`, `currency` and `timezone`. Rows and relations may override `source_url` and `observed_at` with their more specific observation. Both coordinate values are required together; otherwise both remain unknown. A hotel classification must be an integer from one to five; a guest-review score is not a classification.

Do not infer a property's city, currency, timezone, location, size or star grade from its name. Do not include credentials, cookies, tokens, account-user details, subscription settings, rate amounts or guessed OTA mappings. Unsupported input fields are rejected without echoing their values. Source links must use HTTPS on Lighthouse/OTA Insight domains, without embedded credentials or a port. URL query strings and fragments are omitted from saved evidence to avoid retaining session information. Actual hotel identity is preserved separately in `provider_id`.

If the account does not expose a visible total, set `account_subject_count: null` and `subject_list_complete: false`. A complete-list assertion is accepted only when the account count exactly equals the distinct observed subject IDs. Competitor profiles do not increase that subject count. Competitor membership has a separate completeness flag; a fully observed subject list does not prove every configured comparison set was inspected.

Relations are directional, from subject to configured competitor. Both profiles and their relevant roles must be observed. The importer rejects self-relations, missing IDs and wrong roles. Repeated exact relations deduplicate while retaining their evidence. Matching hotel names alone never merge identities.

## Import and projection

```powershell
.\.venv\Scripts\python.exe -m compset.hotel_portfolio --input data/hotel-portfolio/imports/observed.json --data-root data
.\.venv\Scripts\python.exe -m unittest tests.test_hotel_portfolio -v
```

Python interfaces:

```python
from compset.hotel_portfolio import import_hotel_portfolio, load_hotel_portfolio

result = import_hotel_portfolio(observation, data_root)
portfolio = load_hotel_portfolio(data_root)
```

The importer writes `hotel-portfolio/latest.json`, `profiles.csv`, `relations.csv` and immutable content-addressed `history/<sha256>.json` beneath `data_root`. Each file is written through a temporary file and atomic replacement; JSON is published last. A failed JSON publication leaves the prior latest JSON readable. Identical input produces the same snapshot hash. No SQLite schema or existing Aketa data is changed.

Each import is a declared snapshot of its observed scope. A partial import remains partial and may contain fewer records than an earlier snapshot; previous snapshots remain available in history. It does not silently interpret an omitted profile or relation as a deletion from the Lighthouse account. Import a combined observation snapshot when several inspected pages belong to the same inventory. Invoke one importer at a time; this command does not coordinate simultaneous administrative imports.

The read-only `load_hotel_portfolio(data_root)` returns the `hotel-portfolio.v1` contract:

- `profiles`: exact `lighthouse:<provider_id>` identities, public attributes, observed roles, aliases, field-level evidence, conflicts, original source dates and explicit rate coverage.
- `relations`: configured Lighthouse competitor relationships with source evidence.
- `coverage`: the visible account denominator, reconciled subject count/IDs, completeness flags, profile and relationship counts, notes and zero collected rates.
- `provider`, `observed_at`, `source_url`, `warnings` and `schema_version`.

The API projection validates saved IDs and source links and returns only supported fields, including inside evidence objects. Extra account metadata is not exposed. A missing artifact returns `coverage.status: "not_imported"`; malformed artifacts raise `ValueError` for the calling API to report as unavailable. Existing source timestamps are retained instead of being relabeled as a fresh observation when the page reloads.

Exact duplicate IDs merge roles. If duplicate observations disagree on room count, coordinates or another public attribute, the conflict values and their provenance remain visible and the canonical attribute becomes unknown. For title variants, the first observed display title stays visible and all aliases/conflicts are retained. This is an identity-based display choice, not a guessed canonical business name. Coordinate conflicts clear both canonical coordinates together.

## Rate and identity boundaries

Every imported profile has `rate_coverage.status: "not_collected"`, `collection_supported: false` and no OTA mappings. These properties are reconstructed during API projection; editing a saved JSON flag cannot enable collection. No price, availability, occupancy or rate comparison is invented from Lighthouse account membership.

The existing independently configured Aketa dataset remains separate. Even a Lighthouse profile named “Hotel Aketa” is not merged into it by name. A future mapping must use independently verified provider/property evidence and a supported collection contract. The frontend can make every imported hotel selectable while accurately showing its profile and missing rate coverage.

## Verification

Synthetic tests cover exact IDs/leading zeroes, same-name separate properties, role merging, directional competitor relations, account-count reconciliation, partial coverage, source dates, tri-state public fields, conflicting attributes, geographic validation, review-versus-star separation, credential-field rejection, canonical links, atomic failure, immutable history, formula-safe CSV and allowlisted API projection. Real account observations remain under ignored `data/`, never in committed fixtures.
