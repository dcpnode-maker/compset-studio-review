# Order 007: independent one-night job review

Reviewer: Codex sub-agent `/root/discovery`. Implementation owner: root agent. Status: **accepted** for the root-owned one-night planner/orchestrator, CLI branch and accompanying README claims at the source hashes below. The reviewer did not implement application code and edited only its independent regression file and this record. Hotel source preparation by this reviewer is separate work and is not claimed as independently reviewed here.

Reviewed scope: `compset/one_night.py`, the new `one-night-monitor` branch in `compset/__main__.py`, and the related README section. The source quote extractor, calendar preflight and observed-template transport were inspected for integration contracts; their separate source/transport reviews retain ownership of full semantic acceptance. No hotel or Airbnb network requests were made during this review.

## Findings personally reproduced and resolved

1. **Malformed checkpoint JSON raised an unhandled exception.** Valid JSON `[]` or `null` in `one-night-latest.json` caused `AttributeError` at `.get`, even with zero budget and no browser call. Root added typed checkpoint/record guards; the reviewer now proves malformed checkpoint shapes are ignored without network work.
2. **Malformed optional calendar evidence raised an unhandled exception.** A fresh raw source containing `payloads=[null]` failed during locale discovery rather than becoming unknown evidence. Root now checks source/context/payload containers before use. Independent cases for null/list roots, invalid context and null/mapping payloads preserve all 30 subject dates as unknown/proceed, without false skips. Corrupt optional `latest.json` is safely ignored while valid monitored calendar proof remains available.
3. **Cached export metadata was trusted despite reparsing prices.** Deleting only a cached quoted record's `preflight` produced `KeyError` during checkpoint CSV generation. Cached `calendar_run_id` could also be copied rather than rebuilt. Root now constructs a resumed record from the current authoritative plan and source-backed quote context/run/time. The reviewer independently removes preflight, replaces calendar identity with `invented`, and changes the checkpoint price to999999; resumed output restores actual preflight/calendar identity and the precise source amount377.04.

All findings were reported to the implementation owner. Root authored all fixes. No open actionable finding remains in the reviewed orchestration scope.

After initial acceptance, root also restricted discovered locales to strings matching its locale grammar. The reviewer added a raw `request_context.locale={"unexpected":1}` regression; it now remains unknown/proceed for every subject date, without unhashable-value failure or false skip.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

```text
.venv\Scripts\python.exe -m unittest tests.test_one_night_job -v
Ran 5 tests in 1.605s — OK (initial owner-test baseline)

.venv\Scripts\python.exe -m unittest tests.test_one_night_job tests.test_one_night_review -v
Ran 15 tests in 7.351s — OK (after all owner fixes)

.venv\Scripts\python.exe -m unittest discover -s tests -q
Ran 277 tests in 17.174s — OK

.venv\Scripts\python.exe -m unittest tests.test_one_night_job tests.test_one_night_review -v
Ran 16 tests in 6.111s — OK (final locale hardening)
```

The independent file `tests/test_one_night_review.py` contributes eleven tests, with several malformed-source/cache and failure-class subcases. Proof uses temporary source artifacts, mocked browser/HTTP sessions and temporary SQLite databases. It establishes:

- Fresh source-proven negative calendar evidence may skip a contextual stay; stale/malformed sources cannot skip. Departure permission remains distinct from departure-night availability. The owner's departure/minimum-stay cases were personally rerun.
- Every requested target remains one adult and an exact one-night interval. The direct follow-on budget is finite and separate from the single browser bootstrap. Two direct reads produce three verified date cells including bootstrap; the CSV still retains all 60 requested cells, with 57 unrequested amounts blank. A deterministic monotonic clock proves the enforced three-second spacing without real sleeps.
- A pause flag set during spacing prevents the next direct HTTP start and remains on disk. Zero budget and malformed checkpoints do not bootstrap.
- First403,429, transport failure,500 or a200 quote gap stops before a second direct read, preserves the existing quoted cell and records the new cell as unknown. No retry/proxy cycling is performed by the job.
- Cached quote amounts are reparsed from raw source. Missing artifacts, stale raw observation times and a changed two-adult source cannot reuse a quoted checkpoint.
- SQLite append proof preserves the exact historical two-adult `result_json` and all its observation rows, leaves `latest.json` byte-for-byte unchanged, appends two source-verified `one_night_quote` observations, and obtains `PRAGMA integrity_check=ok`.
- The CLI forwards a zero request budget and the three-second default and returns date-cell progress fields.

Source inspection confirms that templates are cleared in `finally`; every checkpoint preserves unknown/unrequested cells; cached skips are recomputed from raw calendar proof; top-level report context identifies `stay_nights=1` rather than presenting a default multi-night interval; and the parser/template/preflight fingerprint participates in cache identity.

## Tested source identity

Initial full-suite identity captured at `2026-09-28T04:29:05.048008+00:00`; final orchestrator/test hashes updated at `2026-09-28T04:31:44.072457+00:00` after the 16-test locale proof. Branch: `codex/one-adult-nightly-coverage`. Git HEAD: `bd9e8be5fe6fbe8e4182fc478b0600015c3fa72d`. Working changes were present, so file hashes identify reviewed source rather than asserting that HEAD alone contains the work. The full-suite result precedes the final locale hardening and the separate new quote-source variant; it is a recorded passing snapshot, not a claim that the evolved whole tree was personally rerun here.

| File | SHA-256 |
| --- | --- |
| `compset/one_night.py` | `ca67dd31a39d063e2556175f701b24abe6dbc940f68f641944a1fd4f6978580e` |
| `compset/__main__.py` | `440b621576b6f45907fd59f944949b2d7fbdbfad22eb6c4177ac042d8d5c2066` |
| `README.md` | `cd447913e41ec9ebfe2491d5bde798338fe7c0be51d4206a6988eee46f569d81` |
| `compset/one_night_rows.py` | `69e683e304db0706d1d3f87ecadec9999486fff714fe78540adc2cca3651747f` |
| `compset/collect.py` | `507cc90005c4d3acb74bccb03e904351d1f1e6730aed7659b36982d141aa88b1` |
| `compset/availability.py` | `0070f0bf2c3a4221eeda062fbf9cc0a9754d9acd556f4fee9cb706108a4cb8d8` |
| `compset/batch.py` | `2b83f6bf189f2cc4d9b74acb98021ccc2b5f400f49c91fc044e8e050d02eca52` |
| `tests/test_one_night_job.py` | `9b8ad1a78d595422a91ccabe597c46498226ea0055545b8305deed1b0c53d102` |
| `tests/test_one_night_review.py` | `34937a59d8ad1c6295170abc2ac2b64b029a6e1828bb2574e58f5479633a3efa` |

The `one_night_rows.py` hash in the table identifies the initial broader proof. The separately implemented parser evolved to hash`542f65fc3f6a4c1a92a1a0bb1f6f25ffb37a2a27d0a9a80db17f27249b249ed5` during a live-source variant correction. Its new `productItemDetail.explanationData` semantics remain subject to the owner's separate independent source review; this orchestration acceptance does not substitute for that proof.

## Limits and live-proof ownership

These are offline executable proofs of orchestration and persistence, not a completed live rate dataset. A quoted one-night stay total remains distinct from a base room nightly rate; unknown tax/fee/cancellation inclusions are preserved. A minimum-stay failure does not prove that a night is booked. The selected set is inherited from the saved comparison and does not establish exhaustive market coverage or a new one-adult discovery search.

The owner reported a successful live one-adult30September–1October canary, run`dbbd393418291785fe4a5afd`, exact377.04AED before taxes, with a verified200 Sections POST replay. That canary was not personally executed by this reviewer; its raw capture and separate transport/source review establish live semantics. A subsequent source variant stopped the job before follow-on HTTP, as designed; parser adaptation and independent review remain owner-managed. The pending finite live collection, any source-specific access limitations and the Hotel Aketa collector remain follow-on work. This acceptance does not claim complete 30-day prices or usable one-adult MMT rates.
