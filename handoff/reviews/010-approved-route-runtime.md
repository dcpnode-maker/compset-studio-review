# Approved route runtime evidence

28 September 2026. Parent personally executed this operational proof after the user's approval and instruction to continue. No implementation code changed; reviews 007–009 remain historical proofs of their recorded revisions.

The existing CompSet dashboard remained on `127.0.0.1:8765`, listener PID 4388, reporting idle and ready. No attempt was made to stop or restart it in this turn. Docker Desktop's status command confirmed it was not running. The supported native proxy mode was used; Docker and unrelated projects were not started.

## Bounded neutral validation

Command: `.venv\Scripts\python.exe routes/kaggle_fetch_validate.py --max-candidates 20 --concurrency 4 --deadline 120 --output routes/working_proxies.txt`.

All five source requests returned HTTP 200. 5,222 lines yielded 4,430 valid unique endpoints. The deterministic first 20 completed validation in 72.95 seconds; three passed certificate-verified HTTPS requests to `https://httpbin.org/ip`. The deadline was not reached. This is evidence only of those three probes at their recorded time. The other 4,410 candidates were not validated; no category or target-success claim is made.

The generated text/JSON manifests were preserved in `routes/data/working_proxies.txt` and `.json`, and the checked-in empty templates were restored after preserving those runtime files. SQLite retains source provenance, probe time, category unknown and transport health. Generated evidence remains local and ignored by Git.

## Native hub and forwarding proof

Started the existing reviewed `routes.proxy_server` with Python in a hidden process, explicit database/list/manifest paths, port 8080, no `--container` and no `--health-checks`. Startup reported three imported routes. Listener verification returned **127.0.0.1:8080**, PID 22452 (launcher 19068). No wildcard bind and no scheduled health probes.

Two bounded HTTPS forwarding attempts used the same explicit local session `approved-neutral-20260928`. First: Requests `ReadTimeout` while establishing the upstream tunnel. One retry on that same sticky route: `ProxyError`; no HTTP success was observed. The pool recorded a proxy CONNECT transport failure. No route replacement occurred and no proxied Airbnb request was attempted. `routes/data/live-canary.json` contains both outcomes; the database contains one pinned session and three imported routes. `PRAGMA integrity_check` returned `ok`.

The hub process is running, but end-to-end proxy usability has **not** been established. Three earlier neutral probe successes do not override the failed forwarding canary. Normal CompSet collection remains direct and independent of the optional hub. Runtime process IDs and route freshness are observations, not permanent guarantees.
