# Aketa provider receipts and cloud status

CompSet Studio remains separate from Yellow. The laptop chat owns its hotel/STR
workflows and data. The user assigned the OpenAI cloud chat
`01a0f33b-8f4c-73f0-b8b9-d07e866e2052` to Yellow PMS/CRS work in parallel.
The parent retains design, integration and acceptance. Delegate bounded work to
faster, cheaper models when the actual host supports them, and review results
before integration.

The saved batch in `data/provider-receipts/20260930/` has 17 researched properties
including Aketa, 230 accepted Booking display offers for nine reviewed identities,
one Ramada Wyndham direct offer, and 30 saved Aketa Google indicative dates.
Detailed arrival window: 30 September–30 October 2026 inclusive. The annual view
has 365 arrival dates through 29 September 2027; missing evidence stays unknown.
This is incomplete annual collection, not verified lowest-all-OTA coverage.

In the running local dashboard, Hotels → **17-property Aketa calendar** opens the
saved yearly/monthly/timeline/profile views at `/aketa-calendar`. The fixed
`/api/intelligence/hotel/provider-receipts` projection validates provider identities
separately from the legacy Aketa-only adapter. JSON/CSV download routes are fixed;
they do not start a collector or accept filesystem paths.

`tools/build_colab_vm_collector.py` prepares
`notebooks/CompSet-Aketa-Colab-VM.ipynb`: one finite 240-second Aketa/30-date canary,
standard CPU requested, no model API, no Drive mount. It records visible resource
limits and exports only sanitized allowlisted results with verified ZIP hashes.
It does not attest cloud placement or implement all 17 properties/365 days.
Build dependency: `nbformat==5.10.4`; public collection dependencies are pinned
inside the notebook. No local credentials, conversation logs or Yellow source
are packaged.

Colab collection execution is unverified. The existing Colab notebook could not be opened
because the browser could not verify saved permissions. The browser also rejected
the local preview's `file:` protocol, so browser visual/interaction acceptance is
pending. Source validation and HTTP checks are separate evidence, not pixel proof.
No browser-security workaround or automatic challenge/proxy fallback is enabled.

The separate OpenAI cloud chat acknowledged the Yellow handoff and performed a
resource/source preflight: affinity has five visible CPUs; cgroup CPU quota is
four cores (`400000/100000`); memory limit is 16 GiB; workspace free disk was
31,942,217,728 bytes (about 29.7 GiB). Its Python/Node/Git versions were
3.12.14/24.19.0/2.52.0. These are observed limits, not an always-on VPS promise or
a measured twofold build-speed improvement. Parent 6.1/ultra was requested but
not independently attested by that host. Bidirectional coordination is authorized
by the user; source/credentials are not shared merely because chat access works.
