# Grok handshake — laptop facts

Snapshot: 2026-10-05, founder laptop. Build paused. This export changes no product source, runtime, database or original checkout/index. No merge, force push, hard reset or new product test was performed. Export sanitization and review-branch commits are snapshot operations.

## Repositories and source identity

- Yellow: https://github.com/dcpnode-maker/yellow — public; default branch main.
- Canonical laptop checkout: E:\YellowWorkspace\Documents\Codex\2026-08-14\cl\outputs\yellow; HEAD 57876f9d1760bb1f06fab77dad38631ee31d5784; dirty; phase-0/founder-context-demo-readiness.
- Live app source: 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773; migration frontier 103; source and runtime are separate from the canonical checkout.
- Unfinished integrated work: C:\Users\astha\yellow-fast-20261005\integration; base 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773; dirty. This candidate is not established as deployed.
- CompSet laptop: E:\YellowWorkspace\CompSetStudio; HEAD 82f1477b3b062fb861be43be68125f0afaeeeff4; phase-0/compset-product-ui; dirty; no configured origin.
- CompSet cloud-source checkout: E:\YellowWorkspace\Data\BuildArtifacts\compset-cloud-handoff-20261003-v1\source; HEAD 098190f6f5105be03907610b2979982193643223; origin https://github.com/dcpnode-maker/compset-studio.git.
- Existing CompSet repository is private, default branch cloud-source-20261003. A secret-free public source export is targeted at https://github.com/dcpnode-maker/compset-studio-review; publication status is in PUBLISHED-BRANCHES.md. The private repository visibility is not changed.

## Versus public 3503b0c (founder reference: 2026-09-07)

The founder supplied 3503b0c and 2026-09-07 as the public comparison reference. It resolves to 3503b0c01f336637d2583963c17b792f6ad59efe, author date 2026-09-07T05:20:01+05:30, merge PR91 (persisted India final-component tax evidence). Per-worktree raw/baseline-3503b0c.txt records whether each local object database resolves it, including full SHA and recorded author date. Those Git dates are not replaced by the founder reference date. Raw log-origin-main-head.txt is the requested pre-fetch comparison; fetch.txt records refresh results. The live SHA, canonical SHA and review snapshots must not be represented as the same source.

## Dump branches

These are snapshot branch names, not release approvals. Actual commit IDs, exclusions, parent preservation and push results are recorded in PUBLISHED-BRANCHES.md and raw/snapshot-branches.json. Clean parent history is retained only if its new reachable history passes the secret scan; otherwise a source-only snapshot is used and the ancestry limitation is stated.

- grok-review/yellow/wip-yellow-34168dc8-20261005-sanitized-v3 — E:\YellowWorkspace\CodexWorktrees\harness-app\yellow — original d29142b39d9d6641a56bb0f8546b5745d5a4e9bc
- grok-review/yellow/phase-7-resource-receiving-20261001-fd4e7066-20261005-sanitized-v3 — E:\YellowWorkspace\Worktrees\phase-7-resource-receiving-20261001 — original 2b096e5f1bf932403a91a4e8f9f135d99465f691
- grok-review/yellow/wip-verification-worktree-62cabbd3-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\hosting\public-demo-autologin-patch-v1\verification-worktree — original 35d2f1c2f1dfba3c6f6353103bdc91e3526b982b
- grok-review/yellow/wip-git-live-order611-source-v2-83b1a0bf-20261005-sanitized-v3 — D:\Yellow\git-live-order611-source-v2 — original e06e400a57485cc10a8a35c21dcb1e01b5a667d1
- grok-review/yellow/wip-yellow-order175-folio-responsive-containment-4b49a215-20261005-sanitized-v3 — C:\Users\astha\Documents\Codex\2026-08-14\cl\outputs\yellow-order175-folio-responsive-containment — original 75a2eba1cd34d0512d010bf3f91230ebed4720e7
- grok-review/yellow/yellow-cd338898-20261005-sanitized-v3 — C:\Users\astha\.codex\worktrees\yellow-harness-controller\yellow — original 09d1a02de56380eaee6116f444ccc1816372505c
- grok-review/yellow/wip-yellow-6abbab39-20261005-sanitized-v3 — C:\Users\astha\.codex\worktrees\pr-repairs\yellow — original d6e57ff7f91ee5ffb6e51f8e6d748294458afa45
- grok-review/yellow/yellow-b762f7ca-20261005-sanitized-v3 — C:\Users\astha\.codex\worktrees\harness-astra-handoff\yellow — original 01c9ffa4d35894c29c93bf66556d6c26848a24be
- grok-review/yellow/yellow-bcadcc61-20261005-sanitized-v3 — C:\Users\astha\.codex\worktrees\bnbme-compset\yellow — original 57876f9d1760bb1f06fab77dad38631ee31d5784
- grok-review/yellow/wip-yellow-a2a8e237-20261005-sanitized-v3 — E:\YellowWorkspace\Documents\Codex\2026-08-14\cl\outputs\yellow — original 57876f9d1760bb1f06fab77dad38631ee31d5784
- grok-review/yellow/wip-runtime-research-flow-1eebbd82-2ce79bcd-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-1eebbd82 — original 1eebbd82d9d3fdf6cb87d6a4685855e1cc619238
- grok-review/yellow/wip-runtime-research-flow-2b096e5f-032c44db-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-2b096e5f — original 2b096e5f1bf932403a91a4e8f9f135d99465f691
- grok-review/yellow/wip-restore-20261001-proof-v2-15702174-20261005-sanitized-v3 — E:\YellowWorkspace\Data\Recovery\RESOURCE-20261001\restore-20261001-proof-v2 — original e06e400a57485cc10a8a35c21dcb1e01b5a667d1
- grok-review/compset/wip-compsetstudio-e8827b49-20261005-sanitized-v3 — E:\YellowWorkspace\CompSetStudio — original 82f1477b3b062fb861be43be68125f0afaeeeff4
- grok-review/yellow/wip-runtime-calendar-0ffb1288-6bef9dda-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-calendar-0ffb1288 — original 0ffb1288a9bb6470da2865c83b4f473377d94f04
- grok-review/yellow/runtime-today-65ba856b-06eb1d25-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-today-65ba856b — original 65ba856b02c9071bd65cad83670d20a34e632787
- grok-review/yellow/wip-crm-tasks-ed8b1f64-20261005-sanitized-v3 — C:\Users\astha\yellow-fast-20261005\crm-tasks — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773
- grok-review/yellow/wip-package-base-c50efc30-20261005-sanitized-v3 — E:\YellowWorkspace\Documents\Codex\yellow-prototype-review-20261002\journey-v2\laptop\housekeeping-shell-composition65-v1\proof\package-base — original HEAD
- grok-review/yellow/order72-onto69-candidate-e3bbd030-20261005-sanitized-v3 — C:\Users\astha\yellow-recovery-20261004\order72-onto69-candidate — original 2b096e5f1bf932403a91a4e8f9f135d99465f691
- grok-review/yellow/wip-3cfa8b3bd6ce5038a4a6947726b80a9bacd26773-4a9ab3d8-20261005-sanitized-v3 — C:\Users\astha\yellow-recovery-20261004\runtimes\3cfa8b3bd6ce5038a4a6947726b80a9bacd26773 — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773
- grok-review/yellow/wip-order72-onto69-candidate-final-e72bd59d-20261005-sanitized-v3 — C:\Users\astha\yellow-recovery-20261004\order72-onto69-candidate-final — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773
- grok-review/yellow/calendar-values-82ec8c66-20261005-sanitized-v3 — C:\Users\astha\yellow-fast-20261005\calendar-values — original ccea8de907bef7268e4168c418afd98fdf452095
- grok-review/yellow/wip-order72-laptop-review-b1f4f321-20261005-sanitized-v3 — C:\Users\astha\yellow-recovery-20261004\order72-laptop-review — original 2b096e5f1bf932403a91a4e8f9f135d99465f691
- grok-review/yellow/wip-stay-billing-289fbe1b-20261005-sanitized-v3 — C:\Users\astha\yellow-fast-20261005\stay-billing — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773
- grok-review/yellow/wip-runtime-today-v3-eb05ba83-26108f78-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-today-v3-eb05ba83 — original eb05ba83ec41664eff0834d98a293fb58e5bb955
- grok-review/yellow/wip-actual-source-restore-86908aab-20261005-sanitized-v3 — E:\YellowWorkspace\Data\Recovery\RESOURCE-20261001\receiving-5f087ef1-v2\actual-source-restore — original 5f087ef1fd9987c45c6aa10eadc6ce63fc79e926
- grok-review/yellow/wip-runtime-research-flow-8bd09c25-964d27f3-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-8bd09c25 — original 8bd09c25bb73083aebaab62d68ea464d838258aa
- grok-review/yellow/wip-runtime-research-flow-9438906c-f842dc3e-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-9438906c — original 9438906c4b8920652d72281daa25e86e9c71bd9d
- grok-review/yellow/wip-runtime-research-flow-5d855ba5-eed5b0b4-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-5d855ba5 — original 5d855ba570636b1821bff385c905fa2ab4f21c24
- grok-review/yellow/wip-runtime-preview-e27da80e-87ee9cf4-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-preview-e27da80e — original e27da80e2e4a55dc653f455adc7b2d271253d20b
- grok-review/yellow/wip-runtime-research-flow-bdc721b2-4b8fb8e6-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-bdc721b2 — original bdc721b26d2811afeff902d537e13761c1212434
- grok-review/yellow/wip-workspace-058b762b-20261005-sanitized-v3 — D:\Yellow\temp\order745\workspace — original HEAD
- grok-review/yellow/wip-runtime-research-flow-312d4f46-a69955ea-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-312d4f46 — original 312d4f46384fc90accc78506d846631133524025
- grok-review/yellow/wip-runtime-browser-session-3039ac-2c9c9ad0-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-browser-session-3039ac — original 3039ac9345503b2e0aec07759d5686493b3ff3c7
- grok-review/yellow/wip-runtime-research-flow-6f315712-bb6e7010-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-6f315712 — original 6f3157126a3e353f931c288b3f5365b0152aed78
- grok-review/yellow/wip-restore-hk-20261001t111103z-0539999111-fa86d407-20261005-sanitized-v3 — E:\YellowWorkspace\Data\Recovery\RESOURCE-20261001\restore-hk-20261001T111103Z-0539999111 — original e06e400a57485cc10a8a35c21dcb1e01b5a667d1
- grok-review/yellow/wip-package-base-a45967f9-20261005-sanitized-v3 — E:\YellowWorkspace\Documents\Codex\yellow-prototype-review-20261002\journey-v2\laptop\shell-layout62-v1\proof\package-base — original HEAD
- grok-review/yellow/wip-workspace-1fe869d1-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\hosting\public-demo-autologin-independent-review\workspace — original 35d2f1c2f1dfba3c6f6353103bdc91e3526b982b
- grok-review/yellow/wip-package-base-v2-3bca38a1-20261005-sanitized-v3 — E:\YellowWorkspace\Documents\Codex\yellow-prototype-review-20261002\journey-v2\laptop\housekeeping-shell-composition65-v1\proof\package-base-v2 — original HEAD
- grok-review/yellow/wip-runtime-research-flow-c1b7c2b8-338e4921-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-c1b7c2b8 — original c1b7c2b80a103b53d29d175e8087776f3cdd776e
- grok-review/yellow/wip-restore-20261001-source-proof-96b7345f-20261005-sanitized-v3 — E:\YellowWorkspace\Data\Recovery\RESOURCE-20261001\restore-20261001-source-proof — original e06e400a57485cc10a8a35c21dcb1e01b5a667d1
- grok-review/yellow/wip-runtime-today-v2-65ba856b-ab03afb7-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-today-v2-65ba856b — original 65ba856b02c9071bd65cad83670d20a34e632787
- grok-review/yellow/wip-runtime-staff-modules-a22290e4-deb9639e-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-staff-modules-a22290e4 — original a22290e42c481651efc9fb65e54ab78b32c28817
- grok-review/yellow/wip-runtime-navigation-93bf7f94-80cd818d-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-navigation-93bf7f94 — original 93bf7f94ce36bbe67404853661ed40f641b5db01
- grok-review/compset/source-d84d8c76-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\compset-cloud-handoff-20261003-v1\source — original 098190f6f5105be03907610b2979982193643223
- grok-review/yellow/wip-runtime-reference-ui-326e80-cf05a827-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-reference-ui-326e80 — original 326e80c8d936362059496e2aa41d28651a05e386
- grok-review/yellow/wip-actual-source-restore-1bbd97eb-20261005-sanitized-v3 — E:\YellowWorkspace\Data\Recovery\RESOURCE-20261001\receiving-b9ba702a\actual-source-restore — original b9ba702a074a487feeafa056abb49abcdcf01ba8
- grok-review/yellow/wip-patch-staging-4f8b58f8-20261005-sanitized-v3 — E:\YellowWorkspace\Documents\Codex\yellow-prototype-review-20261002\journey-v2\11r\original-reservation-journey54-v1\patch-staging — original HEAD
- grok-review/yellow/wip-runtime-research-flow-c2ba896a-a0be730d-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-research-flow-c2ba896a — original c2ba896ab52c34d69617c209a7ad31c630c33a98
- grok-review/yellow/wip-group-inquiry-faa7796a-20261005-sanitized-v3 — C:\Users\astha\yellow-fast-20261005\group-inquiry — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773
- grok-review/yellow/wip-runtime-444072-61c9a487-20261005-sanitized-v3 — E:\YellowWorkspace\Data\BuildArtifacts\yellow-receiving-build-20261001-v1\runtime-444072 — original 444072ffdff2b7745345d88f71b603c17e11ace6
- grok-review/yellow/wip-integration-d7dc049e-20261005-sanitized-v3 — C:\Users\astha\yellow-fast-20261005\integration — original 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773

## What actually runs

Public app: https://yellow-live-app.yellow-dcpnode-1676cc6f.workers.dev/p/6081b544-22a1-534f-a86d-bb1ae0519e14/today?lane=in_house

Read-only /ready observations at 2026-10-05T05:26:41.754705+00:00:

URL: http://127.0.0.1:3184/ready; HTTP 200

```json
{"status":"ready","target":"yellow_runtime_database","build":{"schemaVersion":1,"revision":"3cfa8b3bd6ce5038a4a6947726b80a9bacd26773","expectedMigrationFrontier":103}}
```

URL: https://yellow-live-app.yellow-dcpnode-1676cc6f.workers.dev/ready; HTTP 200

```json
{"status":"ready","target":"yellow_runtime_database","build":{"schemaVersion":1,"revision":"3cfa8b3bd6ce5038a4a6947726b80a9bacd26773","expectedMigrationFrontier":103}}
```

Laptop listeners observed: app 127.0.0.1:3184 PID 13328; PostgreSQL 127.0.0.1:55492 PID 14788. Another Python listener exists at 127.0.0.1:8765 PID 21436; its role is UNVERIFIED. The attempted 127.0.0.1:8080/health endpoint refused connection; this does not prove CompSet has no other runtime. No guest rows, credentials, holds, reservations or financial writes were queried or created.

Final readiness check: 2026-10-05T06:03:07.540681+00:00. Both local and public /ready returned HTTP 200 with the same 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773 / frontier 103 payload. All 61 readable original HEAD and porcelain-status outputs match the initial inventory (raw/worktree-status-final.json). One registered D: worktree is unavailable; no source was fabricated.

## Workflow proof

| Capability | YES / NO / UNVERIFIED | Snapshot evidence |
|---|---|---|
| sign-in | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| availability | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| hold | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| reservation | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| check-in | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| charge | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| checkout | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| guest book | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| IRP live | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |
| compset rate | UNVERIFIED | No fresh end-to-end functional or production-provider proof was performed in this snapshot. /ready is not that proof. |

## File / line counts

Counts cover allowed existing tracked files, excluding secret/data/dependency paths and files over 5 MB. Code lines count LF bytes; untracked files and the handoff are not included in these counts.

- E:\YellowWorkspace\Documents\Codex\2026-08-14\cl\outputs\yellow: 284 files; 122 code files; 23946 code LF lines; HEAD 57876f9d1760bb1f06fab77dad38631ee31d5784.
- C:\Users\astha\yellow-fast-20261005\integration: 2873 files; 1426 code files; 436006 code LF lines; HEAD 3cfa8b3bd6ce5038a4a6947726b80a9bacd26773.
- E:\YellowWorkspace\CompSetStudio: 239 files; 107 code files; 27242 code LF lines; HEAD 82f1477b3b062fb861be43be68125f0afaeeeff4.

## Test paths that are not live acceptance proof

- tests/** and frontend/**/__tests__/** contain source-level/synthetic tests; their existence is not a live workflow result.
- yellow-fast-20261005/evidence76* and yellow-recovery-20261004/*review* are historical verification evidence, not a deployed integrated candidate.
- Database referee/migration test artifacts and isolated fixtures do not establish production IRP, OTA rate freshness, guest-booking delivery or a complete researched PMS UX.
- No product tests were written or run for this snapshot.

## Secret paths — values excluded

- .env and *.env, including .yellow/runtime-database-authority.env.
- .yellow/, .private/, pairing/credential files, OAuth/authtoken files, private keys and keystores.
- postgres-data/, database dumps, backups, *.db, *.sqlite*, browser profiles/cookies and live guest data.
- Public snapshot excludes runtime credentials even where original Git trees tracked them. Original laptop files remain unchanged; source-only sanitization limitations are recorded per branch.

## Chat coverage and provenance

Local Codex: 1,688 records attempted, 1,559 existing rollouts, 129 missing. All are listed in founder-chat/00-CONVERSATION-INDEX.md. ChatGPT: 30 identified conversations, every API-offered cursor attempted; returned-turn coverage is in raw/chatgpt-export-coverage.json. Provider limits and unoffered older history are UNRECALLED / PARAPHRASE. Claude/Cursor history could not be recovered from inspected local transcript locations. Agent-only, delegated and automation prompts are separately labelled; uncertain relay provenance is not silently converted into verified founder authorship. Attachments are referenced, not publicly copied.

## Worktrees, Drive and PRs

61 readable Git locations and one unavailable registered worktree (D:/Yellow/git-live-order611-source) were inventoried. Duplicate Windows extended-path aliases are preserved in the inventory; 52 distinct Yellow/CompSet/source-fragment locations have review branches planned. Seven auxiliary third-party/harness locations are inventoried but not published as Yellow. Raw command outputs preserve status, stash, branches, origin/main..HEAD, diff stats, untracked paths and fetch results. Unborn fragment repositories and unavailable references are explicitly errors, not fabricated commits.

Drive was searched for Yellow and CompSet metadata only. No Drive contents were fetched, cloned, downloaded or changed. Metadata is in raw/drive-*-metadata.json. GitHub PR inventories are raw/yellow-pr-list.json (101 entries, 11 open) and raw/compset-pr-list.json (zero entries); no PR was merged.

## Clone commands

```sh
git clone --branch grok-review/yellow/wip-yellow-a2a8e237-20261005-sanitized-v3 https://github.com/dcpnode-maker/yellow.git yellow-laptop-snapshot
git clone --branch grok-review/yellow/wip-integration-d7dc049e-20261005-sanitized-v3 https://github.com/dcpnode-maker/yellow.git yellow-unfinished-integration
git clone --branch grok-review/compset/wip-compsetstudio-e8827b49-20261005-sanitized-v3 https://github.com/dcpnode-maker/compset-studio-review.git compset-laptop-snapshot
```

Use only clone commands whose publication is confirmed in PUBLISHED-BRANCHES.md. Grok has no implicit laptop access. Source snapshots contain no runtime password or account token.

## Failures and scan

Missing local rollouts, unavailable Claude/Cursor transcripts, ChatGPT item/history limits, unresolved origin/main references and unborn fragment repositories are recorded rather than replaced with summaries. SECRET-SCAN.md records the final scan scope/results. Read-only readiness is the only fresh live proof collected. Original dirty source and untracked work remain on the laptop.

STOP: This is a handoff. No fix sequence is started. Grok is to return the next sequence to the founder.
