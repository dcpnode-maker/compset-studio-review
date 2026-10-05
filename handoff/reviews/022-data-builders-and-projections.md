# Independent review: saved inventory builders and projections

Reviewer: root, independent of the implementation by workspace_data and workspace_ui. Date: 2026-09-28. Scope: the four modules below and their offline test suites; this does not review root's server or UI integration.

Reviewed exact-ID namespacing and evidence retention, profile merge conflicts, missing-core-attribute behavior, radius and optional-service relaxation, unselected candidate retention, source timestamps, unknown versus unavailable price semantics, currency/request separation, bounded pagination, portfolio path containment, account import allowlists and source URL sanitization. No blocking finding in this scope. Accepted as saved-data tooling with explicit partial coverage; this is not evidence of exhaustive discovery or new live rate acquisition.

Personally executed from C:\Users\astha\CompSetStudio:

```
.venv\Scripts\python.exe -m unittest tests.test_portfolio_compsets tests.test_intelligence tests.test_hotel_compset tests.test_hotel_portfolio
Ran 61 tests in 2.314s
OK
exit 0
```

Reviewed SHA256 values:

| File | SHA256 |
| --- | --- |
| compset/portfolio_compsets.py | ce40885e9c13596f114df12cb00781dcab8d93a34e7a46a7a0ed985b6c9f092d |
| compset/intelligence.py | e2cd61e108b606cce258240618d3eed38fb84d13137622196271a448ba25a9f4 |
| compset/hotel_compset.py | ed42b690d8f67e25635fabae784a7d7b253cc02f7f3787fa37a7e98a64fc7737 |
| compset/hotel_portfolio.py | d01488348d23b982d5c4a89d9361bf9d2bb8c1b1e28aa465a499153c807c2029 |

Limits: the Aketa comparison policy is explicitly tailored to its observed city-hotel product, not a universal hotel classifier. Retained OSM features are a bounded source snapshot and are not proof of all operating hotels. Unknown direct-site privacy attributes prevent confirmed Airbnb comparability. Imported Lighthouse identities and account membership are not verified OTA mappings or independently collected rates. Malformed/missing evidence remains incomplete. Browser visual acceptance and persistent runtime activation are outside this review.
