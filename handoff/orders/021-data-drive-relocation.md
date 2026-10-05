# Order 021: move saved project data to E:

Founder request, 28 September 2026: "please move project data to e:\" after C: ran out of space during Order020 UI implementation.

Scope: relocate the existing `C:\Users\astha\CompSetStudio\data` directory to `E:\CompSetStudio\data`; retain the original path through a Windows directory junction. This order and `handoff/reviews/031-data-drive-relocation.md` record execution. Source, virtual environment and Android installation remain in place. No collection, server restart, approval changes or external transfer.

Before the switch, verify adequate destination space, exact resolved paths, no nested reparse points, idle collection status and a complete SHA-256 verified copy. Switch by renaming the original directory, creating the junction, and verifying every file through it. Remove only the verified original backup within the named project root, after a second comparison. If a file changes or cannot be moved, preserve copies and report the incomplete switch. Keep credentials/private pairing files local and do not print their contents.

Status: copy-only partial completion. All1520 files copied to E:,1518 checksum-verified, two locked runtime logs unverified. The move/junction/cleanup was automatically rejected before execution; source remains active on C:. See `handoff/reviews/031-data-drive-relocation.md`. Separate from UI acceptance.
