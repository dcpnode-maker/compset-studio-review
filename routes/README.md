# Local sticky route tools

This is optional route tooling for CompSet Studio. Direct collection already works for the tested subject. The checked-in pool is empty. On 28 September 2026, an authorized local canary fetched all five lists, deduplicated 4,430 endpoints, and validated 20 with four workers: three passed HTTPS httpbin probes. The native hub started on `127.0.0.1:8080` and imported those three routes. Its selected sticky route subsequently failed two bounded forwarding attempts (timeout, then proxy transport error); successful end-to-end forwarding and Airbnb usability remain unverified. No Airbnb request used a proxy. Docker remains stopped; background health checks are disabled. Runtime manifests, SQLite and `live-canary.json` are under `routes/data/`, outside Git. See runtime record 010.

## 1. Run the batch validator on Kaggle

Enable notebook Internet, install `aiohttp`, then upload and execute `kaggle_fetch_validate.py`. The file is self-contained and needs no CompSet package. Kaggle runs batch compute only: it is not the server, does not run Docker, and does not expose a public listener.

```python
%pip install aiohttp==3.14.3
%run kaggle_fetch_validate.py --concurrency 8 --max-candidates 200 --output working_proxies.txt
```

Download **both** `working_proxies.txt` and `working_proxies.json`. The JSON sidecar carries source URLs, validation time, verified HTTPS probe outcome, protocol, latency and observed egress address. Endpoints must be globally routable IPv4 addresses and valid ports. Private, reserved, multicast, malformed, credential-bearing and hostname entries are rejected. Candidates are deduplicated across the five requested public sources.

To validate an explicit operator-supplied list instead of fetching those sources, use `python routes/kaggle_fetch_validate.py --input my_proxies.txt --output routes/working_proxies.txt` from the CompSet root. The same candidate/concurrency/TLS limits apply; no public lists are fetched in this mode. The input file is capped at 2 MB. Its provenance is labeled `operator_supplied` and includes a SHA-256 content digest and byte count with the fixed label `operator-input`; exported manifests never contain the local filename or absolute path. This is a declared operator source, not an assertion that the routes are residential or that they work on Airbnb.

Default validation is 8 concurrent checks, at most 200 candidates, an 8-second timeout and at most one retry of the **same** proxy. Concurrency is capped at 32 and candidates at 2,000. Source bodies and validation bodies are bounded; redirects are disabled. `--deadline 900` limits the validation phase; source fetching adds at most five bounded source requests. Every HTTPS connection verifies certificates. Nothing disables TLS verification.

## 2. Start the laptop hub when wanted

Native mode is also supported and does not require Docker. For the locally validated runtime manifest, run this from the CompSet root only when port 8080 is free:

```powershell
.venv\Scripts\python.exe -m routes.proxy_server --db routes/data/proxies.db --manifest routes/data/working_proxies.json --proxy-list routes/data/working_proxies.txt --port 8080
```

Omitting `--container` fixes the bind to `127.0.0.1`; omitting `--health-checks` disables background probes. Only one local hub may own port 8080. The currently running native process already imported its manifest into SQLite; replacing the checked-in empty templates does not alter that running pool. Future startup should use the runtime paths above. Proxy validation expires after 24 hours and never proves target usability.

Place both downloaded files in this `routes/` directory. From this directory:

```powershell
New-Item -ItemType Directory -Force data
docker compose up --build -d
docker compose logs --tail 20
```

Docker publishes **127.0.0.1:8080 only**. Keep that binding and the dedicated Compose network. Do not publish `8080:8080` or share this service with other hosts/containers. The container listens on its own interface because a container-only loopback bind cannot receive the published port. `--container` is accepted only inside a container. SQLite lives under `routes/data/`. On Linux, the mounted data directory must be writable by UID 10001; Windows Docker Desktop normally handles bind-mount access.

The server imports only endpoints present in both files with a recent successful verified HTTPS probe (within 24 hours), literal boolean success fields, and either known public-source URLs or complete operator-supplied file provenance. Unknown or missing provenance and malformed entries are rejected. Text-only endpoints are not silently trusted. It starts safely with an empty pool and returns 503 until validated routes exist. Compose enables bounded background revalidation: every five minutes, at most 32 routes, concurrency 8, one probe each. Failed routes are retained for audit; routes with three transport failures are ineligible. No health check targets Airbnb. When running without Docker, install the requirements and use `python -m routes.proxy_server --health-checks` from the CompSet root.

## 3. Verify an explicit sticky session

```powershell
curl.exe --proxy http://127.0.0.1:8080 --proxy-user demo-session: https://httpbin.org/ip
curl.exe --proxy http://127.0.0.1:8080 --proxy-user demo-session: https://httpbin.org/ip
```

The same session stays on the same upstream endpoint. Its egress IP can still change if that upstream independently changes it. A new explicit session may receive a different route, weighted toward lower measured latency. Neither action guarantees a distinct exit IP. A failed sticky route returns an error rather than silently selecting another proxy. The proxy username is the explicit session ID; its password is empty. It is routing metadata, not a substitute for loopback isolation.

The production target allowlist is `httpbin.org`, `airbnb.com`, `www.airbnb.com`, `airbnb.co.in` and `www.airbnb.co.in`. Targets must resolve only to globally routable addresses. HTTP accepts read-only GET/HEAD on port 80. CONNECT accepts only port 443, with bounded lifetime, idle time and transferred bytes. Request headers are bounded and ambiguous HTTP framing is rejected. The server uses `asyncio` streams for CONNECT because aiohttp's web server is not a turnkey CONNECT tunnel. It never decrypts or intercepts TLS; the requesting client remains responsible for certificate verification.

## 4. Replay a freshly observed Airbnb read

From the CompSet root, after installing `routes/requirements.txt`:

```powershell
.venv\Scripts\python.exe -m routes.airbnb_scraper --listing 1567889913136387224 --checkin 2026-10-17 --checkout 2026-10-20 --adults 1 --currency AED --session-id research-1
```

Choose future dates when running later. This command first performs CompSet's normal **direct** browser observation, holding discovered request templates and session headers only in memory. It then tests **one** allowed observed GET through the explicitly selected local sticky route. It prints normalized JSON, preserves unknown fields and makes no claim that a stay total is a nightly price. The direct and routed contexts are distinct; a session-bound request may legitimately fail when replayed through another route.

This deliberately does not invent a `StaysSearch` endpoint contract, supply an old hardcoded API key, or generate city-search variables. The callable `execute_observed(template, session_id=...)` accepts fresh templates from the existing observer. Request URLs, credentials, cookies and session headers are never written to route logs or SQLite. The wrapper keeps TLS verification enabled, bounds response size, disables redirects, paces its one request after discovery, and makes **no automatic retry** through another route.

HTTP 401/403/429 and recognized HTML challenges halt the attempt. For HTTPS the tunnel cannot inspect target statuses: the wrapper reports them through a loopback JSON control endpoint. The server then halts that session and records a target-wide cooldown without marking the proxy transport broken. Arbitrary browsers/clients that do not report outcomes cannot provide this guarantee; use the wrapper or integrate its `report_block` call. CONNECT denial or connection failure is recorded separately as an upstream transport problem. After a target cooldown expires, resuming a halted session requires explicit `python -m routes.pool --reset-session research-1`; this keeps the same route. Never create replacement sessions to work around a target block.

## Limits and deviations from the proposed specification

Public free proxies have **unknown route category** unless independently verified. No residential label, 90% datacenter statistic, ban immunity or success-rate claim is made. Many may fail, disappear, observe plaintext HTTP, or return altered data. An HTTPS httpbin success proves only that probe, at that time; it does not establish Airbnb usability, anonymity or trustworthiness. The target may reject every route. No proxy service guarantees success.

500-way validation and per-request switching are replaced by finite low-concurrency validation and explicit sticky sessions. Background probes are local Docker work, never a Kaggle server. Notebook runtimes are ephemeral and their limits depend on the current service configuration; rerun the batch when needed rather than assuming a guaranteed duration or scheduling automatic daily external activity. This package installs no scheduler.

Use only authorized low-volume research and follow the target's current terms and access policies. The tools stop on access/rate limits and provide no CAPTCHA solver, fingerprint escalation or challenge bypass. No spending or paid infrastructure is needed. Direct access remains available; proxies are optional and are not a fix for missing source data.

## Local proof

From the CompSet root: `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_routes*.py" -v`. Tests use in-memory manifests, fake clients and loopback fake upstream servers. Test-only dependency injection never becomes a production option for permitting private proxy endpoints or destinations.

API references: [aiohttp client proxy support](https://docs.aiohttp.org/en/stable/client_advanced.html#proxy-support), [Python asyncio streams](https://docs.python.org/3/library/asyncio-stream.html), [Requests advanced usage](https://requests.readthedocs.io/en/latest/user/advanced/).
