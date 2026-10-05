# Review 024: owned-device desktop client

Reviewer: `/root/ota_review`, independent of the root implementation. Scope: Order015 `routes/owned_devices.py`; reviewed local urllib32.8.0 connection code as well as the application. No production client implementation was edited by this reviewer. Review accepted for local code integration on2026-09-28 after the corrections below.

## Findings corrected

- Registry loading originally accepted malformed or unknown session references and unbounded/unsafe health fields. Root added bounded session IDs/references, strict health field/type/time/destination/origin/latency validation, and validated status output.
- Python accepted numeric values as IPv4 addresses, both for a paired route and a JSON echo. Root now requires literal strings; unknown/private/forwarded-chain echo values cannot produce healthy state.
- Stale independently loaded registries could overwrite sticky bindings or use outdated healthy observations. Root added a process-safe compare-and-write lock, stale-state checks before assignment/manager/status/mutation, and poisoned failed-write instances. A stale existing session or a repeated assignment after rejected persistence now fails explicitly; no new phone is substituted. Reload is explicit.

## Personally executed proof

Command from `C:\Users\astha\CompSetStudio`:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_owned_devices_review tests.test_owned_devices -q
```

Final result: **21 tests passed in5.960seconds**, exit0, using Python3.13.1 and urllib3 2.8.0. Includes13 independent tests and8 implementation tests.

The four independent TLS tests generate short-lived self-signed test certificates with the already available local JDK, keep their private keys only in a temporary directory, and delete those fixtures afterward. All transport is redirected through a socket pair; there is no phone, DNS resolution, internet request, public listener or persistent service. The actual urllib3 TLS and CONNECT implementation runs with certificate verification enabled.

- A separately trusted proxy certificate with the wrong pin reaches the real fingerprint check, fails, and receives **zero HTTP/authentication bytes**. Trusting that fixture chain is deliberate test injection to isolate the pin check.
- An untrusted proxy certificate receives no authentication bytes.
- A correctly pinned proxy can receive CONNECT authentication while an untrusted target certificate still fails before any target HTTP request.
- With separate test trust for both layers, the fixed `https://httpbin.org/ip` request traverses the synthetic encrypted tunnel; the target sees `GET /ip` and no proxy authorization header or encoded pairing credential. The production OS trust store is never changed.

Other proof covers the fixed probe, redirects/retries disabled, bounded response size, resource closure, missing tokens, sanitized failures, no token persistence, malformed sessions/health, literal IP validation, stale/future health rejection for routing, sticky reuse, no failure fallback, stale write rejection and mandatory explicit reload.

## Reviewed hashes

| File | SHA256 |
|---|---|
| `routes/owned_devices.py` | `1a7fc25abfc46a17b5212dff093cec62a5512a722c88a1e14c6a10d46e6c464d` |
| `tests/test_owned_devices.py` | `37d2fb4b11cdf05b05646f31689b213ab5c374008211267f7789ac384fb462a5` |
| `tests/test_owned_devices_review.py` | `1179eabeac190702a08b5f8d546071fdd0361a45cb6fca55d6508c7f44067f5e` |

## Limits

This is desktop-client and isolated transport acceptance. It does not prove Android installation, a physical phone certificate handshake, cellular routing, mobile IP identity, carrier compatibility, remote deployment or accommodation-site usability. Android implementation review is separate. No existing dashboard runtime was restarted and no denied browser/runtime action was retried. The optional TLS fixture tests skip when the local JDK fixture generator is absent; this reviewer run executed all four with no skips.
