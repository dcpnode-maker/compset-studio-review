# Secret scan — snapshot scope

The chat/handoff export was scanned using Gitleaks 8.30.1 and explicit redaction patterns for passwords, tokens, authorization headers, connection credentials, private keys, long encoded credential payloads and labelled guest/patient identifiers. Recovered sentences retain the marker «REDACTED-SECRET» in place of excluded values.

Final chat/handoff scan before source-branch preparation: exit 0, zero Gitleaks findings. The initial scan found 76 credential-like candidates in 26 files; these were conservatively redacted. Candidate counts are not proof that every match was a live credential. No candidate value is included in this report.

Each source snapshot is independently scanned before publication. Current source candidates are redacted only in the export; the original laptop files and indexes are unchanged. New reachable parent history is scanned separately. Private CompSet history is excluded from its public source export. Per-branch scan results, ancestry limitations and push receipts are in PUBLISHED-BRANCHES.md and raw/snapshot-branches.json.

Never exported: .env, .yellow/runtime-database-authority.env, .yellow runtime state, .private files, credentials/pairings, private keys/keystores, postgres-data, dumps, data stores, browser profiles/cookies, raw conversation databases or image attachments. Secrets in an excluded path are reported by path only.

Limits: an automated secret scan is not proof against every possible secret format or personal identifier. No live guest records were fetched. The source and founder-chat exports preserve provenance limits and redaction markers rather than inventing missing text.

No secret-bearing commit has been pushed by this snapshot operation. If publication is blocked, that branch remains local until a secret-free source-only snapshot exists. No force push, merge or secret rotation is performed speculatively.

GitHub push protection blocked the first attempts despite a zero-result Gitleaks scan. GitHub identified OpenRouter API-key and GCP service-account-bound API-key formats in chat transcripts. Both repositories had zero review refs after the rejected attempts. Additional provider-specific and password/Markdown/hyphen redaction was applied. Unsafe local review histories are retained locally with a normal removal commit and are never published; the public retry uses new source-only -sanitized-v3 branches. No protection bypass, force push, merge, original-source edit or speculative credential rotation was performed.
