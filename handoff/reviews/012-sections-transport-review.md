# Order 007 independent Sections transport review

Reviewer: Codex sub-agent `/root/scrapling_research`. Implementation owner: `/root/transport`. Scope: the new observed `StaysPdpSections` POST capture/replay and public request-context handling in `compset/collect.py`, and the implementation owner's new POST/context-verification changes to `batch.retarget_template`.

Independence boundary: the reviewer previously authored the original GET-only batch retarget helper and the new pure `one_night_rows` extractor. This record does **not** claim an independent review of those original implementations or the extractor. It reviews the transport agent's changes. Root owns the one-night job, broader integration and full-suite proof. During this review the reviewer edited only `tests/test_sections_transport_review.py` and this record.

Status: **accepted for the reviewed transport changes**, with no open findings. No external requests, browser/CUA sessions or live target calls were made by the reviewer. Tests use fake browser callbacks, fake HTTP clients and temporary batch-persistence fixtures.

## Reviewed behavior

- The POST admission boundary permits only the observed persisted `StaysPdpSections` operation on an exact allowed HTTPS Airbnb origin, with a 64-character hexadecimal path hash and the expected top-level body shape. Mismatched operation names/hashes, caller-supplied GraphQL documents, arbitrary POST operations and duplicate query overrides are rejected. The transport does not manufacture an endpoint or hash.
- Browser capture uses each finished request's own `request.response()` and `post_data_json`. It does not join responses to a URL-keyed request-body map. This matters because different Sections requests share the same URL.
- Public context comes from the actual URL/body. Repeated agreeing aliases are accepted; inconsistent or invalid aliases are omitted and recorded in `request_context.conflicts`. Both observed encoded listing-ID types are understood. Guest counts, currency, dates and identifiers are not borrowed from run defaults.
- Replay deduplication includes method, URL and the complete observed body. Distinct date/guest bodies are retained. Copies supplied to the HTTP client cannot mutate the stored template or the provenance subsequently attached to the response. Templates, headers and full request bodies remain in memory; public results exclude request credentials and opaque query data.
- POST retargeting requires the original observed party/currency to match the requested context. It changes existing listing/date fields, preserves identifier representation, hash, flags, guest fields, heatmap interval and unrelated host ID, then verifies the resulting actual context. Missing/ambiguous source context fails closed.
- Access/rate-limit statuses stop replay immediately. Explicit HTML challenges and challenge text in GraphQL errors stop the HTTP loop; the browser path also prevents date-control actions, direct replay and template export after a recognized challenge. Ordinary successful public data mentioning a captcha is not treated as a challenge.

## Finding resolved before freeze

Source inspection during implementation found that a status-200 HTML challenge would previously receive only `not_json`, allowing later replay requests. Browser request-finished capture also needed to set a stop condition before subsequent actions/replay. The reviewer sent both concerns to the implementation owner before code freeze. The owner added explicit challenge detection and stopping in both paths. This was a source-review finding; the reviewer does not claim to have run a failing pre-repair test. The reviewer personally executed the new HTTP and browser challenge regressions after the repair, and both passed.

## Reviewer-executed proof

Working directory: `C:\Users\astha\CompSetStudio`.

Command:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_sections_transport tests.test_collect tests.test_batch tests.test_sections_transport_review -v
```

Result: **43 tests passed in 1.351 seconds**, personally executed after the implementation owner's freeze. This includes 10 new implementation transport tests, 16 collector regressions, 8 batch regressions and 9 independent reviewer tests.

The independent tests cover:

1. Mutation/document injection, conflicting hash, wrong operation, query override and foreign-origin rejection.
2. Conflicting and invalid guest/date/currency aliases removing disputed values rather than choosing the last value.
3. Same-URL distinct-body replay, exact duplicate suppression, client-side mutation isolation and credential exclusion.
4. Status-200 HTML challenge stopping before a second POST.
5. POST 401/403/429 stopping without response-body retention or a follow-up request.
6. Browser challenge preventing date-control search, HTTP-client construction and template export.
7. Same-URL responses completed in reverse order retaining their own one-adult/two-adult request evidence.
8. POST retargeting preserving hash, encoded-ID type, unrelated fields and original input.
9. Refusal to retarget originally conflicting guests, dates or listing IDs.

## Reviewed hashes and limits

SHA-256 at the reviewed freeze:

| File | SHA-256 |
| --- | --- |
| `compset/collect.py` | `507cc90005c4d3acb74bccb03e904351d1f1e6730aed7659b36982d141aa88b1` |
| `compset/batch.py` | `2b83f6bf189f2cc4d9b74acb98021ccc2b5f400f49c91fc044e8e050d02eca52` |
| `tests/test_sections_transport.py` | `d52a217b62186a4d3cbdb1bdfc1d4f8a809ff1590f8bbb2450794135a147ce87` |
| `tests/test_sections_transport_review.py` | `be159c1e1355a94f1a8b786a104594b2587f4a074b9104a674ae9c43c93dab62` |

Offline proof establishes the implemented request/response and replay boundaries for the observed source shape. It does not establish future Airbnb schema stability, that an arbitrary caller-provided template was actually observed, or that every challenge format is recognized. Live request capture/response evidence and one-night price semantics are separately validated by root. A successful response may still contain no usable price; this transport does not promote HTTP 200 to a verified quote or a booking guarantee.
