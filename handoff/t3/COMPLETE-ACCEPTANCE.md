# CompSet Studio complete acceptance run

Status: PREPARED; no new test pass is claimed by this document. Order019. Scope: CompSet Studio. Profile: independent-review.

The founder requests a complete test through T3, with Kaggle used where supported. T3's owner must first establish a real execution capability and exact worker identity. A signed-in notebook, compiled model, generated recommendation, queued task or successful manual preview is not a test execution receipt.

## Source and transfer

- Reviewed source baseline: `0fd4b10dc1d6ccaad2edba1e24900f1b7f1cdd7d`.
- Local reviewed archive: `data/exports/source-review-0fd4b10/CompSetStudio-source-0fd4b10.zip`.
- ZIP SHA-256: `1dc3f25f6dcc6582cdf535f32c74a87e4e4dbf528007eef0ab13ee3221939ce0`.
- The ZIP contains 223 tracked files plus two generated review documents. Verify its manifest and hashes before executing tests. Read `REVIEW-FIRST.md`.
- It excludes saved observations, credentials, private proxy/pairing state, SDKs and build products. Keep these exclusions when using Kaggle. The separate text companion is for reading, not execution.
- The live checkout now has untracked restart/log files. Preserve them and exclude them from remote transfer and test commands. Do not execute the unreviewed restart script.
- Use a private isolated workspace for tests, report its Python/Node/JDK versions and dependency installation result, and bind receipts to the actual file hashes. Missing dependencies are failures to establish that gate, not permission to skip it silently.

## Required matrix

| Gate | Required evidence | Execution location | Initial status |
| --- | --- | --- | --- |
| S01 source integrity | Exact source/artifact manifest, no unreviewed/private additions, environment versions | T3 host and receiving worker | Pending |
| P01 complete Python suite | All discovered `tests/test_*.py`, exit status, every failure/error/skip, retained output | Isolated test executor | Pending |
| J01 complete JS suite | All five checked-in `tests/test_*.js`, including performance fixture flag; report optional tests separately | Isolated Node executor | Pending |
| C01 parser/semantic contracts | Changed/missing fields, null prices, exact vs indicative totals, restrictions vs unavailable vs unknown, failed responses | Python fixtures and contract suites | Pending |
| C02 state and collection contracts | Deduplication, resume/checkpoint binding, cache expiry, cancellation, single-job admission, no fetch on saved-data navigation | Isolated Python/JS integration tests | Pending |
| C03 isolation and input safety | Property/source identity, route guards, path bounds, CSV formula defense, stale asynchronous result rejection | Existing Python/JS review suites | Pending |
| J02 actual saved projections | STR/hotel rendering and exports against retained local evidence; no real data uploaded | T3 laptop execution | Pending |
| R01 serving source and APIs | Source identity of already serving app, HTTP success for workspace API and assets, expected response schemas | Permitted read-only laptop verification | Pending; earlier runtime stale |
| U01 desktop UI | Actual STR/hotel navigation, filters, details, calendar/table/map, exports, unknown/error/empty states | Permitted real browser | Pending |
| U02 mobile/accessibility | Narrow and medium viewport, touch targets, readable calendars, scrolling, keyboard/focus, modal restoration, contrast | Permitted real browser | Pending |
| U03 performance | Cold/warm timings, representative response sizes, p50/p95, request counts, cache reuse, stale-request rejection, map instance reuse | T3 laptop; fixture and real browser results separate | Pending |
| D01 existing coverage audit | Freshness and supported denominators for BnBMe Dubai/Riyadh/London, Airbnb identities, Aketa peers, imported hotels | Local saved-data read | Known incomplete |
| D02 fresh job acceptance | Supported fresh/pause/resume with correct selected job/context and partial-error reporting; bounded exact request scope | Authorized source collection path | Pending |
| D03 rates/compset completeness | Observed exact source IDs, room/bath/location/amenity comparison reasons, relaxation/radius decisions, dated contextual prices | Source-specific data evidence | Known incomplete |
| A01 portable Java core | Core, independent gateway and independent DNS64 suites; compile and all main-class results | JDK executor | Pending |
| A02 Android build | Current APK build/lint/signature/version/SDK metadata with artifact hash | Existing Android build environment | Pending |
| A03 physical Wi-Fi route | Current APK identity, selected transport, pinned TLS/authenticated neutral HTTPS request, bounded request count | Actual opted-in phone and laptop | Historical bounded pass; current retest pending |
| A04 physical cellular route | Selected Android network, successful neutral egress, same-network DNS/socket; distinct exit only if actually measured | Actual opted-in phone and laptop | Known DNS64 failure |
| A05 Stop/cancellation/lifecycle | UI Stop state, active authenticated transfer teardown, no listener/service, network loss, reconnect, background/long session | Actual opted-in phone and laptop | Partially unverified |
| A06 device/version/multi-route coverage | Real tested OS/device matrix; Wi-Fi + cellular/dual-SIM concurrency only with overlapping successful probes | Available physical devices/emulators as appropriate | Unverified; vNext master not implemented |
| V01 independent acceptance | Reviewer executed relevant verification; findings bound to run/source/artifact/test evidence | Separate reviewer | Pending |

## Source test entry points

Run from the isolated source root. Install the checked-in locked Python dependencies in that environment through its normal permitted setup. Do not install Playwright browsers or launch source collectors merely to make fixture tests run.

```text
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_dual_workspace.js tests/test_dual_workspace_review.js tests/test_rates_workspace.js tests/test_root_workspace_review.js tests/test_workspace_responsiveness_review.js
```

Set `COMPSET_DUAL_BENCH=1` for the JS performance fixture. Its DOM-construction counts are not browser latency and do not establish a speed advantage over PriceLabs or Lighthouse.

On the laptop only, use `COMPSET_DUAL_REAL_DATA=1` for the actual saved STR/hotel projection case after confirming the expected files exist. The rates workspace additionally supports `COMPSET_WORKSPACE_FIXTURE` pointing to its expected existing local projection. These tests are conditionally not registered when flags are missing; zero reported skips therefore does not imply full saved-data coverage. Never upload the saved projections to Kaggle as a shortcut.

Read-only inventory found 45 Python test files and five JS test files. Static counting is not an execution count. The JS baseline registers 76 cases; benchmark mode adds one, and the two saved-data options add one each. A complete applicable laptop run therefore includes up to 79 JS cases. Do not execute every Python file under `tests/`: `probe_subject_details.py` is a separate live Airbnb probe, not part of the unit suite.

The existing Windows Java entry point is `android-gateway/scripts/run-core-tests.ps1`; its current script runs the implementer `CoreTests` only. To satisfy A01 on a Linux/Kaggle executor with JDK21 available, compile and execute all three suites from the source root:

```bash
set -euo pipefail
proof_dir="$(mktemp -d "${TMPDIR:-/tmp}/compset-java.XXXXXX")"
sources=(
  android-gateway/app/src/main/java/com/compset/gateway/core/*.java
  android-gateway/tests/*.java
  tests/android/GatewayReviewerProof.java
  tests/android/Nat64ReviewerProof.java
)
javac --release 8 -Xlint:all -d "$proof_dir" "${sources[@]}"
java -ea -cp "$proof_dir" com.compset.gateway.core.CoreTests
java -ea -cp "$proof_dir" GatewayReviewerProof
java -ea -cp "$proof_dir" Nat64ReviewerProof
```

These suites use portable standard Java/fake sockets. Historical counts to reproduce or explain are 181 core assertions, 101 independent gateway assertions and 456 independent DNS64 checks. They do not substitute for Android behavior on a physical phone.

The Python TLS reviewer fixture hardcodes `android-gateway/.tools/jdk-21.0.12.1+1/bin/keytool.exe` and `java.exe`: without this Windows fixture runtime its four TLS cases class-skip. Node-backed Python reviews also skip if Node is unavailable. The real Aketa research test skips without ignored local research files. Record each omission; do not disguise missing executables with filenames or remove guards to force a pass. Run the Windows-specific fixture against the retained local environment or admit a separately reviewed portability fix.

The dual-workspace actual-saved-data case hardcodes `.venv/Scripts/python.exe` and reads local `data/`. It belongs on the Windows laptop at this baseline. A passing cloud process exit with skipped required cases or omitted saved-data flags is partial acceptance.

## Live checks and unchanged boundaries

The user reports that activation was completed elsewhere; this is not yet independently established by this run. Test the current serving runtime only through an actually permitted path. Do not execute the previously rejected restart/browser action through another provider, invoke the unreviewed new restart script, or change approval controls. An unavailable verification path stays unverified.

Keep source data and source states truthful: unavailable is not booked; a skipped/restricted/failed quote is not zero or unavailable; direct-site rates are not Airbnb rates; a record is not a complete compset. Past saved counts are comparison baselines, not fresh claims of corporate or market completeness.

Live collection is a separate bounded gate from offline tests. Record source, property IDs, dates, currency, occupancy and request budget before dispatch; preserve source restrictions and explicit partial outcomes. Viewing saved data must never initiate collection. Do not use random public proxies or an unverified phone route to make tests pass.

Physical phone checks require the phone to be present and explicitly operated within the user's test scope. Kaggle cannot establish a USB device result, laptop browser behavior or an Android transport choice. A six-to-seventeen Android compatibility claim requires evidence beyond a single installed API35 device.

## Result receipt and completion rule

Every gate records: task/run IDs, executor, UTC start/end, exact source and artifact hashes, environment/runtime versions, command or reproducible steps, exit/result, passed/failed/errored/skipped/omitted counts, evidence path and unresolved finding IDs. Keep secrets and raw private records out of shared summaries. Preserve original output locally with appropriate access.

Allowed gate outcomes: `passed`, `failed`, `blocked`, `not_run`, `not_implemented`, `partial`. Overall complete acceptance requires every applicable required gate passed on the actual reviewed candidate, with independent acceptance. A narrower source-test pass may be reported as such; it must not be relabeled 'fully tested'. Historical results remain dated and cannot substitute for the new run. Explicitly identify future, unimplemented master-node features rather than counting them as tested.
