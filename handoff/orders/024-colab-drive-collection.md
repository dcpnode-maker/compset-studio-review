# Order 024 — CompSet collection through Colab to Ankit Drive

30 September 2026 founder request: run CompSet collection in parallel with harness
work through Google Colab, retaining data in the stated 5 TB Google Drive.

## Scope

- `tools/build_colab_collector.py`, `tests/test_colab_collector.py`, generated
  `notebooks/CompSet-Aketa-Colab.ipynb`, `docs/colab-drive-collection.md`.
- This order and `handoff/reviews/031-colab-drive-collection.md`.
- Review the existing Google collector and package only its code/public target
  metadata. Exact original/portable source digests, no private repo or data export.
- Standard CPU Colab, ankitg.owa identity/storage verification, normal explicit
  Drive mount; one finite new Aketa 30-day canary with direct source access.
- Run locally on the Colab VM, then copy a finite allowlist of sanitized outputs
  to a new private run folder and re-read every file to verify its SHA256. Preserve
  output across interrupted sessions; no destructive moves or overwrites.
- Record requested Aketa plus six evidenced peers, 365-day target, 30-day OTA
  detail and ten monthly breakup samples as planned coverage, not acquired data.
  The existing adapter proves only Aketa/one adult/INR/30-day indicative minima.
  Peer identity adapters, future-month navigation and breakup checks remain pending.

## Boundaries and completion

No denied local server restart/browser workaround, proxy/IP rotation, challenge
bypass, repeated source retry, paid services, booking writes, secrets/session export,
arbitrary cloud code, new model or GPU. The Kaggle trial is independent; do not
restart or repurpose its kernel. Existing source/dirty edits remain untouched.
Google sign-in or consent requires normal supported human interaction; do not
claim connector access establishes Colab login, 5TB quota or filesystem mounting.
Offline format/code/parser tests do not prove Colab execution or Drive round-trip.
