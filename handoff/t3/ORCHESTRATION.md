# Astra-led T3 delivery policy

Founder instruction, 28 September 2026. Scope: the Yellow Ecosystem, CompSet Studio and Universal Harness project tasks in T3. Profile: Astra-led, Sol-coordinated, cost-aware parallel delivery with independent review.

This is the requested standing project policy. It does not claim that a runtime setting, model connection or worker dispatch has already been applied. The receiving owner records actual configuration and execution receipts separately. It does not change the Codex Ultra Orchestration plugin, approval controls or the selected model of this chat.

## Roles

- **Astra: technical lead.** Own requirements, architecture, priorities, bounded work decomposition, integration decisions and evidence-based final acceptance. Initiate independent Sol lanes when the work and available resources justify them. Resolve difficult or high-risk decisions; do not repeatedly reread routine implementation context.
- **Sol: execution coordinator.** Translate the accepted scope into concrete tasks, dependencies, budgets and proof requirements. Dispatch to eligible implementation/test/review models, reconcile results, fix ordinary failures within scope, and bring only material decisions or unresolved evidence to Astra. Maintain one authoritative task state and avoid conflicting writers.
- **Eligible models/workers: bounded execution.** Select the fastest sufficiently capable verified model for each job. Prefer free or already included access. Use cheaper models for routine implementation, scaffolding, test execution and summaries; escalate difficult debugging, foundational design and consequential reviews when evidence calls for it. A model being listed does not establish access, quota, executable tools or suitable capability.
- **Independent reviewer.** Must not have implemented the reviewed change. Inspect the exact diff/artifact and personally execute relevant proof. A worker's reported success alone does not establish acceptance.

## Efficiency rules

Use measured task success, wall time, tokens/credits, retry rate and rework to choose models. Reuse source hashes, test receipts and cached unchanged analysis; send bounded context and diffs rather than repeatedly sending the whole project. Parallelize genuinely independent work within actual resource capacity and quota. Do not start every available model for every task or duplicate an uncertain dispatch. Use checkpointed explicit handoffs when changing providers.

T3 remains the user UI and execution-session host; Paperclip owns durable task/run state. Sol can continue routine authorized work without repeated approval questions. Credentials, new spending, business/legal decisions and irreversible external actions remain with the founder. Existing project orders, privacy boundaries and execution controls persist. No automatic recurring schedule is created by this policy.

## Required visible records

Each project task shows requested and active lead/coordinator, exact verified model/backend identities, capability/quota status, current assignments, source/artifact/test bindings, latest accepted checkpoint, open blockers, next action and cumulative run cost/time where available. Distinguish configured, queued, running, failed, blocked, reviewed and accepted. Record unavailable cost telemetry as unknown.

The first CompSet assignment is the complete acceptance matrix in `COMPLETE-ACCEPTANCE.md`. Do not mark it fully tested until applicable required gates pass. An inference-only Kaggle worker can assist reasoning/review; actual test execution requires an executor with Python/Node/JDK and verifiable command results.
