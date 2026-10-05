# Order 007 final independent price review

Reviewer: Codex sub-agent `/root/price_review`. Implementation owners: root (orchestration and persistence), `/root/scrapling_research` (pure price extraction) and `/root/transport` (observed Sections transport). This reviewer authored none of the application code and edited only this review record. No external requests, browser sessions, live data changes or process start/stop actions were performed.

Status: **accepted at the file hashes below; no open actionable finding**. This is acceptance of the reviewed implementation and offline proof, not a claim that the pending live collection has complete rates.

## Personally executed verification

Working directory: `C:\Users\astha\CompSetStudio`.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Result: **293 tests passed in 20.002 seconds**. This reruns the transport review, calendar preflight, exact price variants, malformed cache guards, pacing/budgets, stop behavior and SQLite history tests against the final source snapshot. The tests for both `one_night_rows.py` and `normalize.py` dependency revisions personally passed: each revision appends distinct derived evidence without overwriting the previous unknown observation or immutable run/source; repeating the same revision does not duplicate its evidence. Existing subject `latest.json` preservation and SQLite `integrity_check=ok` assertions also passed.

I read order 007 and reviews 011/012, inspected the final extractor, its shared money/identity helpers and the final orchestration/cache/versioning path. I then independently loaded each of the three actual saved source captures in a separate Python assertion script and called `extract_one_night_quotes(raw['payloads'], raw['context'])` directly:

| Saved source run | Exact one-night amount | Tax inclusion | Rate plan |
| --- | --- | --- | --- |
| `343bad0eb58d2776bc06f695` | AED 650.40 | Unknown | Unknown; BasicPriceDetail |
| `dbbd393418291785fe4a5afd` | AED 377.04 | Explicitly before taxes | Unknown |
| `dfb0c0e003403a4bb860c98b` | AED 610.36 | Unknown | Selected plan 51, Non-refundable |

The last capture separately retains plan 3, Refundable, at AED 650.40, including its source cancellation text. It is not treated as a conflicting selected price or averaged with the selected amount. The first capture supplies an exact `HighlightExplanationLineItem` named `Price after discount`; no tax conclusion is inferred from that label. The second supplies the explicit `377.04 total before taxes` accessibility label. The final capture's selected option agrees with the exact semantic total in `productItemDetail.explanationData`.

The independent saved-capture script asserted one quoted row per capture, exact amounts and tax flags, contextual `one_night_stay_total` classification, unknown fee/base amounts, actual one-adult/listing identity on every retained source, and the two separate optionality prices. For each capture it changed all actual request envelopes to two adults while leaving the run defaults unchanged: extraction returned no quote. It separately changed response statuses to 429: extraction returned no quote, without inventing unavailability. Input objects and original source file bytes were unchanged after all assertions. All three saved-capture proofs passed.

## Semantics and safeguards inspected

- Actual request provenance must explicitly agree on listing, check-in/out, every guest count, currency and an observed English locale. Conflicting aliases or default run context alone cannot verify a price.
- Exactly one night and one adult are required. Rounded primary display values and unit-price arithmetic do not supply a total. A one-night stay quote remains distinct from a base nightly rate.
- Explicit false availability, duration conflict, contradictory exact totals, selected option identity/amount conflicts and differing observations of the same rate option yield unknown main amounts. Distinct cancellation plans retain separate evidence.
- Unknown fee, tax and cancellation inclusions remain unknown. Exact source paths, raw line items, request context and observation times remain attached to derived prices.
- The parser evidence hash includes both `one_night_rows.py` and its shared `normalize.py` dependency, with named dependency boundaries. Current checkpoints are reparsed from raw source, and versioned SQLite observations are appended rather than replacing historical interpretations.
- Cached planning metadata is rebuilt from the current plan. Calendar skips require fresh raw proof; restriction failures remain distinct from booked nights. Browser bootstrap, serial spacing, pause, finite direct-request budget and contract/access stops remain in place.

## Verified source identity

Hash capture: `2026-09-28T04:54:26.751107+00:00`. Branch: `codex/one-adult-nightly-coverage`. Git HEAD: `bd9e8be5fe6fbe8e4182fc478b0600015c3fa72d`. Working changes were present; these hashes identify the tested files, not HEAD alone.

| File | SHA-256 |
| --- | --- |
| `compset/one_night.py` | `9f2efb9f6d4fb232baee04b3f4bb9f8166414f2aaf90edc5a1b4ed12fb98dfea` |
| `compset/one_night_rows.py` | `bc29ef92694409723b0445aedb6752cf5d2829d81aeca92eaf112545437a407e` |
| `compset/normalize.py` | `f2dc2a946c9ef9a1a6b62fe1daf930c2005372f7bb1aa843a908f056fb56f7b7` |
| `compset/collect.py` | `507cc90005c4d3acb74bccb03e904351d1f1e6730aed7659b36982d141aa88b1` |
| `compset/batch.py` | `2b83f6bf189f2cc4d9b74acb98021ccc2b5f400f49c91fc044e8e050d02eca52` |
| `compset/availability.py` | `0070f0bf2c3a4221eeda062fbf9cc0a9754d9acd556f4fee9cb706108a4cb8d8` |
| `compset/__main__.py` | `440b621576b6f45907fd59f944949b2d7fbdbfad22eb6c4177ac042d8d5c2066` |
| `tests/test_one_night_rows.py` | `1465220f506c2b1e1ab1be989a0aa5f0126577b1599d93105db14debf60734bd` |
| `tests/test_one_night_review.py` | `98a2756ac8aa500c74ceca1bef028b41d95f5e9a2350cef56e80fc0e1e589f37` |
| `tests/test_one_night_job.py` | `9b8ad1a78d595422a91ccabe597c46498226ea0055545b8305deed1b0c53d102` |

Combined price parser evidence hash: `0465f86a6fcf0ca60c66ab525e49d7ff8a9def76c5d138f8d79f826ebdc60f4a`.

| Raw source file | SHA-256 |
| --- | --- |
| `data/runs/343bad0eb58d2776bc06f695/source.json` | `3415721dd9edbcef8186e1e3d6e36edcffe1c41967db907ca716d6c1e6ee22d6` |
| `data/runs/dbbd393418291785fe4a5afd/source.json` | `4a544a6179b62af0458d698aafc5936d69e8dadeed66d1159e53fd54123dee6b` |
| `data/runs/dfb0c0e003403a4bb860c98b/source.json` | `2fe47ee1fdc795799454b510fdee806be6d5076b0219a737f6e43197c31137ac` |

This review does not certify live future source stability, final bookability, exhaustive market discovery, completed 30-day prices or Hotel Aketa collection. Live collection results remain separately reported by the implementation owner.
