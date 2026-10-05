# You are working on the GitHub repository: dcpnode-maker/yel…

{
  "id": "01a00f34-2732-7b82-ad79-ccfb5ed045ab",
  "title": "You are working on the GitHub repository: dcpnode-maker/yel…",
  "created_at": 1786961471,
  "updated_at": 1786961472,
  "cwd": "\\\\?\\C:\\Users\\astha\\Documents\\Codex\\2026-08-14\\cl\\outputs\\yellow",
  "thread_source": "user",
  "agent_path": null,
  "archived": 0
}

Source: local Codex rollout, read without modifying it. Dates are UTC. Founder-labelled entries are original user-role records in a user thread; relays identified by metadata or text are labelled separately. Unidentifiable relays remain a provenance limitation. Assistant entries are verbatim claim excerpts, not independent proof.

## 2026-08-17T10:11:15.643Z — FOUNDER: verbatim recorded user message

<recommended_plugins>
Here is a list of plugins that are available but not installed.

- Airtable (airtable@openai-curated-remote)
- Apollo.io (apollo@openai-curated-remote)
- Asana (asana@openai-curated-remote)
- Atlassian Rovo (atlassian-rovo@openai-curated-remote)
- Base44 (base44@openai-curated-remote)
- Box (box@openai-curated-remote)
- Canva (canva@openai-curated-remote)
- Cloudflare (cloudflare@openai-curated-remote)
- Codex Security (codex-security@openai-curated-remote)
- Figma (figma@openai-curated-remote)
- Gmail (gmail@openai-curated-remote)
- Google Calendar (google-calendar@openai-curated-remote)
- Google Drive (google-drive@openai-curated-remote)
- Granola (granola@openai-curated-remote)
- HeyGen (heygen@openai-curated-remote)
- HubSpot (hubspot@openai-curated-remote)
- HyperFrames by HeyGen (hyperframes@openai-curated-remote)
- Linear (linear@openai-curated-remote)
- Lovable (lovable@openai-curated-remote)
- Monday.com (monday-com@openai-curated-remote)
- Neon Postgres (neon-postgres@openai-curated-remote)
- Notion (notion@openai-curated-remote)
- OpenAI Developers (openai-developers@openai-curated-remote)
- Outlook Calendar (outlook-calendar@openai-curated-remote)
- Outlook Email (outlook-email@openai-curated-remote)
- PostHog (posthog@openai-curated-remote)
- Remotion (remotion@openai-curated-remote)
- Replit (replit@openai-curated-remote)
- Semrush (semrush@openai-curated-remote)
- Sentry (sentry@openai-curated-remote)
- SharePoint (sharepoint@openai-curated-remote)
- Slack (slack@openai-curated-remote)
- Stripe (stripe@openai-curated-remote)
- Supabase (supabase@openai-curated-remote)
- Superpowers (superpowers@openai-curated-remote)
- Teams (teams@openai-curated-remote)
- Vercel (vercel@openai-curated-remote)
- Wix (wix@openai-curated-remote)
- Zotero (zotero@openai-curated-remote)
</recommended_plugins>
# AGENTS.md instructions for C:\Users\astha\Documents\Codex\2026-08-14\cl\outputs\yellow

<INSTRUCTIONS>
# AGENTS.md — adapter for OpenAI Codex (and other AGENTS.md-reading tools)

## STOP. Read `PROJECT.md` first.
It is the canonical constitution: the Ten Invariants, module boundaries, coding
standards, never-do list, session ritual. **This file adds only your role.** If this
file ever contradicts PROJECT.md, PROJECT.md wins.

Then run `./state.sh` — ground truth, identical for every agent.

## Your role: BUILDER

Claude Fable 5 writes the orders and reviews the result. You implement.

- **Work only from an order** in `handoff/orders/`. No order → no code.
- Branch `phase-N/slug`; commits prefixed `[codex]`; PR when green.
- Run `./setup.sh --db-only` **before** opening the PR. `11 passed, 0 failed` or it
  isn't reviewable. Paste the output in the PR body.
- **Stay inside the order's Scope list.** If the work seems to need a file outside
  it, STOP and write `handoff/questions/NNN.md` — never widen scope silently.
- **STOP and ask** whenever you touch: migrations, occupancy claims, journal/posting
  logic, fiscal chains, RLS, tenant scoping, a new state transition, a new table, or
  a new event. Those are architect calls, not yours.
- Never merge your own PR. Never edit `migrations/0001_init.sql`.
- Before deciding anything: `grep -i "<topic>" DECISIONS.log`. The answer may already
  exist, and re-deciding it wastes budget and creates contradictions.

## Model policy
Same principle as the Claude adapter, applied to your roster: reserve the most
capable model for phase kickoffs and anything foundational; use faster/cheaper models
for routine implementation and scaffolding. Configure in `~/.codex/config.toml`.
MCP servers for this project: `.codex/config.toml` (see `docs/CODEX.md`).

Review authority and tiers: `handoff/ROSTER.md`. The loop: `docs/WORKFLOW.md`.

</INSTRUCTIONS>
<environment_context>
  <cwd>C:\Users\astha\Documents\Codex\2026-08-14\cl\outputs\yellow</cwd>
  <shell>powershell</shell>
  <current_date>2026-08-17</current_date>
  <timezone>Asia/Calcutta</timezone>
  <filesystem><workspace_roots><root>C:\Users\astha\Documents\Codex\2026-08-14\cl\outputs\yellow</root><root>C:\Users\astha\.codex\visualizations\2026\08\17\01a00f34-2732-7b82-ad79-ccfb5ed045ab</root></workspace_roots><permission_profile type="disabled"><file_system type="unrestricted" /></permission_profile></filesystem>
</environment_context>

## 2026-08-17T10:11:15.749Z — FOUNDER: verbatim recorded user message

You are working on the GitHub repository:

dcpnode-maker/yellow

Before writing any code:

1. Read and fully understand:
   - PROJECT.md
   - AGENTS.md
   - BUILD-PLAN.md
   - UI-SPEC.md
   - docs/YELLOW-ARCHITECTURE-V1.md
   - handoff/orders/014-yellow-v1-interactive-prototype.md

2. Treat those documents as authoritative.

3. Follow all Ten Invariants and repository rules.

4. Do NOT modify:
   - database migrations
   - production schema
   - occupancy logic
   - ledger logic
   - RLS/security model
   - event contracts
   - state machines

unless explicitly instructed by a future order.

Mission:

Build the first high-fidelity interactive prototype for Yellow Hospitality Operating System.

This is NOT a PMS dashboard.

The prototype must demonstrate:

- Hospitality Operating System philosophy
- Big-picture operational awareness
- Progressive disclosure
- Guest/Property Graph
- Reservation Workspace
- Guest Workspace
- Operations Workspace
- Revenue Workspace
- Comp Advantage Workspace
- AI Agent Workspace
- Universal Command Center
- Voice/Command parity architecture
- Peek → Drawer → Workbench interaction model

The experience should feel closer to:

Salesforce
- 
Linear
- 
Notion
- 
Bloomberg Terminal
- 
Hospitality PMS
- 
AI Operating System

while remaining hospitality-native.

Requirements:

- Extremely fast.
- Minimal dependencies.
- Clean architecture.
- Mobile responsive.
- Keyboard friendly.
- Accessible.
- No mock enterprise clutter.
- No unnecessary menus.
- Infinite depth through progressive disclosure.

Research Context:

The long-term platform is being informed by:
- Oracle OPERA
- OPERA Cloud
- OWS APIs
- Mews
- Cloudbeds
- Salesforce
- Airbnb
- Stripe
- Shopify
- Modern AI agent systems

Do not copy their UI.

Extract principles.

Deliverables:

1. Working prototype implementation.
2. Architecture notes.
3. Screenshots.
4. Design rationale.
5. Pull Request.

Before opening PR:

- Run tests.
- Run type checks.
- Verify no invariant violations.
- Verify no schema drift.

Create a draft PR with a clear summary of:
- What was built
- What remains
- Architectural decisions made

Work autonomously.
Optimize for long-term platform quality, not short-term feature count.


