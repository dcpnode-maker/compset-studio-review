# Colab → Ankit Drive collection

Order024 is separate from Yellow and the finite Kaggle coding trial. It packages
only reviewed public collector code, never private source, credentials, pairing
material or conversation logs. Local collector files and server are unchanged.

Build/validate on this laptop:

```powershell
python tools/build_colab_collector.py
python -m unittest tests.test_colab_collector -v
```

Open `notebooks/CompSet-Aketa-Colab.ipynb` in Colab under ankitg.owa. Use standard
CPU, not a Kaggle-connected local runtime. Google documents that Drive filesystem
mounting is not supported on local-runtime routes. Sign in and explicitly consent
to the notebook's Drive mount. The notebook checks account identity and quota
before mounting; it does not buy storage or compute. Drive consent permits broad
notebook access, though this code only writes a new research run folder.

The notebook runs its child collector in Colab VM storage to avoid sync-browser
event-loop conflicts and many tiny Drive writes. It copies only eight allowed
sanitized files into `MyDrive/CompSetStudio/collection-runs/<unique-run>/`,
re-reads their SHA256, and retains a receipt. No overwriting or destructive moving.
An interruption stops the run; collection is not automatically repeated.

This first canary supports Aketa/one adult/INR/30 indicative calendar dates only.
The requested six peers/365 days/30-day OTA detail/monthly ten-date tax and fee
checks remain planned, not acquired. Google minima do not prove the lowest rate
over all sites; absent supplier/room/tax/cancellation details remain unknown.
Identity/adapters for peers and normal future-month navigation need verification
before extending the live collector. No previously denied local restart/browser
action, proxy fallback or challenge bypass is enabled.

Normal account selection established Ankit Colab sign-in. Ankit Drive's storage
UI confirms5TB entitlement (429.64GB used,4.58TB remaining). The notebook is
uploaded privately: [open in Colab](https://colab.research.google.com/drive/1bdOUztYA5oaMswtbEpz9gIQ-4fl7thYN).
CPU runtime is now allocated; the first cell waits at Google's credentials
consent dialog. Allow was not clicked and the human decision is pending. Mount, execution
and Drive round-trip remain unverified. Saved30September Aketa evidence exists
locally but has not been presented as new Colab collection. Receipt031 tracks
the actual separate gates.

Sources: [Colab FAQ](https://research.google.com/colaboratory/faq.html),
[Playwright browsers](https://playwright.dev/python/docs/browsers),
[Scrapling dynamic sessions](https://scrapling.readthedocs.io/en/latest/fetching/dynamic.html).
