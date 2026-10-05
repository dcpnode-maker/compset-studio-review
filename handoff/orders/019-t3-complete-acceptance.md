# Order 019: T3 project tasks and complete CompSet acceptance

Status: IN PROGRESS, 28 September 2026. Source baseline: `0fd4b10dc1d6ccaad2edba1e24900f1b7f1cdd7d`.

The founder requests a complete test of CompSet Studio through T3, using a Kaggle worker where supported, and three visible T3 tasks for continuing Yellow Ecosystem, CompSet Studio and Universal Harness. This replaces the earlier small-test request. Scope/profile: CompSet Studio acceptance coordination / independent-review. Task creation for the other two projects organizes work; it does not expand their implementation orders.

## Scope

- This order and `handoff/t3/`: task briefs, complete acceptance matrix, exact execution receipts, independent findings and delivery status.
- Existing tests and source may be read, packaged from the already reviewed snapshot and tested in isolated environments through the receiving workflow. No application implementation edits are authorized by this order; findings requiring fixes become a separate scoped order.
- Coordinate with the existing harness owner chat `01a02df3-c84f-7773-a169-dec0e20c9da6`; it owns T3 task creation and worker dispatch. Root must not concurrently operate its Kaggle notebooks.
- Preserve all existing working files, observations and untracked `Restart-CompSet.ps1`, `server_stderr.log`, `server_stdout.log`. They are outside the reviewed source export and are not test entry points.

## Boundaries and proof

The source-only ZIP from Order018 is the cloud candidate. No private observations, credentials, browser sessions, pairing material, raw conversation logs or unreviewed new files are included. Kaggle model inference is not shell/test execution, and neither proves the laptop UI or phone behavior. Record unsupported capabilities explicitly.

Do not repeat previously rejected restart/browser actions through T3, Kaggle or another provider, change approval controls, or accept a model opinion as authorization. This order is for distinct permitted verification and review. No commercial operation, perpetual automation or new spending is authorized. The previously paused handover heartbeat remains paused.

A test result must identify its project/task/run, source and artifact hashes, executor, environment, command, exit code, counts, skipped/omitted cases and evidence location. Missing, blocked, skipped or failed required gates prevent a complete-pass claim. An independent reviewer must inspect the results and personally execute relevant verification before final acceptance. Do not erase earlier failure evidence when a later test passes.

## Acceptance

1. Three actual, visible T3 tasks with stable IDs and links/navigation, verified after creation; no duplicate Codex tasks.
2. Full test matrix in `handoff/t3/COMPLETE-ACCEPTANCE.md`, with cloud/local/device boundaries and known failures.
3. Actual execution receipts from the documented T3/Kaggle workflow, or exact blocked/unsupported states where execution is unavailable. Queued work is not completion.
4. A final report separates source tests, serving runtime, real browser/mobile behavior, collection/data completeness and Android physical-device coverage. Only the scopes actually proved may be marked passed.
