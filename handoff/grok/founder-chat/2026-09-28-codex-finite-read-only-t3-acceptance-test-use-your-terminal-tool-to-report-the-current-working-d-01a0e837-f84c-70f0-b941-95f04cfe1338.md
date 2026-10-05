# Finite read-only T3 acceptance test. Use your terminal tool to report the current working directory, git branch and HEAD for this harness implementation checkout, and read only the first 12 lines of PROJECT.md. Do not edit any file, inspect credentials, use the browser, run long tests, contact other agents or make network requests. Reply in English in at most 100 words. If a tool is denied, report that; do not bypass it.

{
  "id": "01a0e837-f84c-70f0-b941-95f04cfe1338",
  "title": "Finite read-only T3 acceptance test. Use your terminal tool to report the current working directory, git branch and HEAD for this harness implementation checkout, and read only the first 12 lines of PROJECT.md. Do not edit any file, inspect credentials, use the browser, run long tests, contact other agents or make network requests. Reply in English in at most 100 words. If a tool is denied, report that; do not bypass it.",
  "created_at": 1790602377,
  "updated_at": 1790602937,
  "cwd": "\\\\?\\E:\\YellowWorkspace\\CodexWorktrees\\harness-app\\yellow",
  "thread_source": null,
  "agent_path": null,
  "archived": 0
}

Source: local Codex rollout, read without modifying it. Dates are UTC. Founder-labelled entries are original user-role records in a user thread; relays identified by metadata or text are labelled separately. Unidentifiable relays remain a provenance limitation. Assistant entries are verbatim claim excerpts, not independent proof.

## 2026-09-28T13:33:09.266Z — INJECTED CONTEXT

# AGENTS.md instructions for C:\Users\astha\.codex\worktrees\harness-app\yellow

<INSTRUCTIONS>
# graphify
- **graphify** (`~/.Codex/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

--- project-doc ---

# AGENTS.md — adapter for OpenAI Codex (and other AGENTS.md-reading tools)

## STOP. Read `PROJECT.md` first.
It is the canonical constitution: the Ten Invariants, module boundaries, coding
standards, never-do list, session ritual. **This file adds only your role.** If this
file ever contradicts PROJECT.md, PROJECT.md wins.

Then run `./state.sh` — ground truth, identical for every agent.

## Your role: PRIMARY IMPLEMENTATION AND COORDINATION OWNER

**Effective 2026-08-23** (founder directive, `DECISIONS.log` D-91; full context in
`handoff/CODEX-HANDOFF.md`), Codex owns Yellow's implementation end to end. Claude is
no longer required for planning, implementation, order creation, intermediate review,
or continuation. Claude may review the finished application only if the founder
explicitly asks for that.

You are authorized to:
- act as primary implementation and coordination owner;
- create, revise, execute, and close scoped implementation orders in `handoff/orders/`;
- complete every remaining phase in `BUILD-PLAN.md` and `handoff/ROADMAP.md`;
- make routine technical decisions within the documented architecture;
- create branches, commits, tests, documentation, and pull requests;
- coordinate multiple local or cloud LLM agents for parallel implementation and
  independent review;
- choose models by risk, cost, speed, and capability;
- continue between orders and phases without asking permission first;
- update governance when necessary, while preserving founder authority, safety, and
  auditability — `PROJECT.md` remains the canonical constitution, unchanged.

**Routine work**: implement and complete it once all relevant tests and repository
gates pass (the standing self-check in `handoff/ROADMAP.md`; the referee in
`PROJECT.md`).

**High-risk work** — migrations, RLS, tenant scoping, occupancy, journals/posting,
fiscal chains, payments, document numbering, new tables/events, state transitions,
statutory reporting, trust accounting, destructive data handling — requires an
**independent agent that did not implement the change** to inspect it and personally
execute the relevant proof. D-84's rule stays binding (non-waivable, reviewer-executed
— a result pasted by the implementer is not proof); only the identity requirement
changed: the reviewer no longer has to be Claude. Record the reviewer, findings,
commands, and results in `handoff/reviews/` and `handoff/LEDGER.md`.

Ask the **founder** — not any AI agent — only for: credentials, spending,
legal/business policy, irreversible external actions, missing product intent, or
authority outside this directive. Claude's absence is never treated as a blocker.

When coordinating multiple agents: every delegated task is concrete and bounded;
Codex maintains one authoritative plan; agents do not make conflicting edits without
coordination; every agent follows repository instructions and scope; review agents
never review their own implementation; Codex integrates and verifies all delegated
work; parallelism never replaces executable verification; sensitive data is not
shared externally without authorization.

## Standing rules (unchanged by the directive)

- **Work only from an order** in `handoff/orders/`. No order → no code.
- Branch `phase-N/slug`; commits prefixed `[codex]`; PR when green.
- Run `./setup.sh --db-only` **before** opening the PR. `11 passed, 0 failed` or it
  isn't reviewable. Paste the output in the PR body.
- **Stay inside the order's Scope list.** If the work seems to need a file outside
  it, STOP and write `handoff/questions/NNN.md` — never widen scope silently.
- Never merge your own PR. Never edit `migrations/0001_init.sql`.
- Before deciding anything: `grep -i "<topic>" DECISIONS.log`. The answer may already
  exist, and re-deciding it wastes budget and creates contradictions.

## Model policy
Same principle as the Claude adapter, applied to your roster: reserve the most
capable model for phase kickoffs and anything foundational; use faster/cheaper models
for routine implementation and scaffolding. Configure in `~/.codex/config.toml`.
MCP servers for this project: `.codex/config.toml` (see `docs/CODEX.md`).

Review authority and tiers: `handoff/ROSTER.md`. The loop: `docs/WORKFLOW.md`.

## Imported Claude Cowork project instructions

overview work done by other ai models.

</INSTRUCTIONS>
<environment_context>
  <cwd>C:\Users\astha\.codex\worktrees\harness-app\yellow</cwd>
  <shell>powershell</shell>
  <current_date>2026-09-28</current_date>
  <timezone>Asia/Calcutta</timezone>
  <filesystem><workspace_roots><root>C:\Users\astha\.codex\worktrees\harness-app\yellow</root></workspace_roots><permission_profile type="managed"><file_system type="restricted"><entry access="read"><special>:root</special></entry></file_system></permission_profile></filesystem>
</environment_context>

## 2026-09-28T13:33:32.954Z — FOUNDER: verbatim recorded user message

Finite read-only T3 acceptance test. Use your terminal tool to report the current working directory, git branch and HEAD for this harness implementation checkout, and read only the first 12 lines of PROJECT.md. Do not edit any file, inspect credentials, use the browser, run long tests, contact other agents or make network requests. Reply in English in at most 100 words. If a tool is denied, report that; do not bypass it.

## 2026-09-28T13:33:36.255Z — assistant claim excerpt

AGENT-INFERRED: I’ll run the requested local read-only checks and stop if the terminal tool denies access.
AGENT-INFERRED: (Only one non-empty line was recorded.)

## 2026-09-28T13:42:11.676Z — assistant claim excerpt

AGENT-INFERRED: The terminal check succeeded.
AGENT-INFERRED: - Working directory: `C:\Users\astha\.codex\worktrees\harness-app\yellow`
AGENT-INFERRED: - Branch: `phase-0/harness-app`
AGENT-INFERRED: - HEAD: `b0156db5c4399a833d9d80055ebcb3935e4dc575`
AGENT-INFERRED: The first 12 lines of `PROJECT.md` say it is the canonical constitution, takes precedence over agent adapters, and begins the “What Yellow is” section.

