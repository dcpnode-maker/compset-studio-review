# Independent review: root workspace integration

Reviewer: `/root/workspace_data`, 28 September 2026. Implementer: `/root`.

Scope reviewed: root-owned fixed intelligence GET routes and static allowlist, collection-only controller bridge, and lazy default application shell. This review does **not** independently accept the reviewer-authored portfolio builder, intelligence projections or Lighthouse hook. It also does not independently accept the separate dual-workspace frontend module.

Result: accepted for local code integration after one confirmed refresh race was fixed. Runtime activation, live browser rendering and visual/mobile fidelity remain unverified. No production server was restarted, no browser action was attempted, and no source collection was started by these tests. HTTP proof used isolated temporary-data servers on operating-system-assigned ports; browser behavior used a Node DOM model and the actual application script in a VM.

## Finding and correction

The reviewer created a deterministic regression for a job completing while an earlier saved-data read was pending. `acceptJob()` attempted the required completion reload, but `reloadSaved()` returned because `state.loading` was true. When the older response resolved, no further read occurred. This could leave old rates visible after a completed job. The new regression failed with one read instead of two.

The root implementer added a coalesced `queuedSavedReload` follow-up, cleared on destroy. The reviewer personally reran the failing test after the change and added a destroy-with-queued-read case. Both pass. No outstanding finding remains within the reviewed scope.

## Personally executed proof

- `node --test tests/test_rates_workspace.js tests/test_root_workspace_review.js`: **34 passed, 0 failed**. The eight independently authored cases cover delayed-status destruction, destruction during fresh preflight, target freezing during a view switch, destruction after an already-authorized POST, completion during an earlier read, unsupported imported-hotel collection targets with fixed Resume identity, queued-read destruction, and actual lazy app startup/navigation.
- `.\.venv\Scripts\python.exe -m unittest tests.test_root_routes_review tests.test_intelligence_server tests.test_server -q`: **10 passed, 0 failed** in 5.623 seconds. The four independently authored HTTP cases prove exact typed dispatch, encoded duplicate/unknown/oversized query rejection before projection, origin/Host rejection for every new read route, no collector dispatch or data writes, generic read-error responses, and exact static-file allowlisting.
- `node --check compset/static/app.js`: exit 0.

The application-shell VM proof executes the actual `app.js`, confirms only the dual view mounts initially, confirms no legacy read/poll begins from a collection-status callback before legacy initialization, and observes the first `/api/status` read only after explicit legacy navigation. A second legacy navigation does not initialize it again. This is executable control-flow proof, not visual QA.

## Reviewed file hashes (SHA-256)

| File | SHA-256 |
| --- | --- |
| `compset/server.py` | `46c25d2d8ba2194447d4a21761cb4385571efa7d099519b6ad4c03278b2b03ce` |
| `compset/static/rates-workspace.js` | `dc716d41a895c1f6d4ea845a0dee0c4d08c033ab321dd7e2e6b24dd2be7b8cec` |
| `compset/static/app.js` | `789604ae00fbe4c08b38472070eb1b9eef414bdcc9a41a81fb285b0ae18e3c09` |
| `compset/static/index.html` | `4f8334a303b8c9ac38671949ef4971ed27469d2f9dc2cf05ed8f7bb3206744d9` |
| `compset/static/style.css` | `5f9a3960d97cca4a72bf7bd83baefe0f988d2ae99b5ea836553347bac3a740b1` |
| `tests/test_rates_workspace.js` | `7628c47045a324c4d58647e269f46a0e818818b40d16318aa6eb43c50f53e0c9` |
| `tests/test_intelligence_server.py` | `a32de6f4140f72880a7ec7334ec769315ff32595be31d0f4f0ae3d18ef4dab9e` |
| `tests/test_root_workspace_review.js` | `e3dd417e25f7051d97f1ba1bf580968bab7dfad1ae3232bd4b5129c6302a647f` |
| `tests/test_root_routes_review.py` | `1a0c1e43320c9a900a65fe5b59ebfd67f9d05749e787eaa03287079634b8b8c3` |
